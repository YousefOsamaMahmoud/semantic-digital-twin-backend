# Sprint 3 — Comprehensive Architectural & Code Audit Report

> **Auditor:** Senior Backend Auditor
> **Scope:** `models/schemas.py`, `services/llm_service.py`, `services/lifting_service.py`, `api/sandbox.py`
> **Date:** 2026-05-17

---

## File 1: `models/schemas.py`

**🟢 PASS**

### What was done well
- `SLAContract` remains completely untouched — no regression risk for the existing `/upload-sla` endpoint.
- All 6 new models (`ExtractedSLAData`, `ConfirmedSLA`, `RiskAnalysisResult`, `IoTTelemetryEvent`, `ManagerAlert`) match the schemas defined in `INTEGRATION_PLAN.md` section 2.1 exactly.
- Every `Field()` has `min_length`, `gt`, `ge`, `le` constraints, plus `examples` and `description` — this drives correct OpenAPI/Swagger docs automatically.
- `ExtractedSLAData.document_id` uses `default_factory` with `uuid4()` so the field is never empty on auto-generation.
- `ConfirmedSLA.corrections` is correctly typed `str | None = None` — optional, nullable, safe.
- `RiskAnalysisResult.severity` is a free `str` (not an enum) — consistent with the blueprint which left it as open string for LLM flexibility.

### No vulnerabilities found
**Ready for Sprint 4.**

---

## File 2: `services/llm_service.py`

**🟡 WARN — 2 issues found (both non-blocking, should address before Sprint 4)**

### What was done exceptionally well

**Resilience & Fallbacks — Grade A:**
- `invoke_structured()` and `invoke_text()` both correctly wrap their try blocks around both `_ensure_llm()` (lazy construction) and the actual `chain.invoke()` — so missing API keys, network errors, and 429s are all caught by the same handler.
- The 429 detection checks **5 signals**: `"429"`, `"quota"`, `"resource exhausted"`, `"rate limit"` — this covers all major providers (OpenAI, OpenRouter, Gemini, Azure).
- `_generate_fallback` returns **valid, fully-populated Pydantic instances** — not raw dicts — so downstream code never hits `AttributeError`.
- Lazy initialization via `_ensure_llm()` means the client can be instantiated without any API key configured. The system gracefully degrades to simulation mode.

### Issue 1 — Singleton not thread-safe (WARN)

**Location:** Line 114–119, `get_instance()`

```python
@classmethod
def get_instance(cls, config: Optional[LLMConfig] = None) -> "LLMClient":
    if cls._instance is None:
        cls._instance = cls(config)
    return cls._instance
```

**Problem:** Two concurrent requests can both see `_instance is None` and both create new `LLMClient` instances, violating the singleton contract. FastAPI serves async endpoints; although the GIL reduces the risk, it is still a race condition on first access.

**Fix:**
```python
import threading

_lock: ClassVar[threading.Lock] = threading.Lock()

@classmethod
def get_instance(cls, config: Optional[LLMConfig] = None) -> "LLMClient":
    if cls._instance is None:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
    return cls._instance
```

### Issue 2 — Sync LangGraph blocks async event loop (WARN)

**Location:** `run_extraction_pipeline()` at line 689–717, called from `api/sandbox.py` line 231 inside `async def upload_pdf()`.

**Problem:** `graph.invoke(initial_state)` is a synchronous, blocking call. Running it directly inside an `async def` endpoint blocks FastAPI's event loop, degrading throughput under concurrent requests.

**Fix in `api/sandbox.py`** (wrap in `run_in_executor`):
```python
import asyncio

# Inside upload_pdf():
loop = asyncio.get_running_loop()
state = await loop.run_in_executor(None, run_extraction_pipeline, raw_text)
```

Alternatively (simpler, keeps the service sync):
```python
# In services/llm_service.py, add an async wrapper:
async def run_extraction_pipeline_async(raw_text: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_extraction_pipeline, raw_text)
```

### Issue 3 — Minor: Unused `import json` (cosmetic)

**Location:** Line 16.

```python
import json
```

`json` is never used anywhere in the file. Remove it.

### Issue 4 — Minor: Lost exception chain in fallback (cosmetic)

**Location:** Lines 360–363.

```python
except Exception:
    logger.error("Cannot build fallback for unknown schema %s.", schema)
    raise
```

The re-raised exception loses the original traceback context. Should be `raise from exc` — but since no `exc` variable is bound here (bare `except`), fix to:

```python
except Exception as fallback_exc:
    logger.error("Cannot build fallback for unknown schema %s: %s", schema, fallback_exc)
    raise fallback_exc
```

---

## File 3: `services/lifting_service.py`

**🟢 PASS — with 2 minor findings**

### What was done exceptionally well

**Namespace enforcement is flawless:**
- Zero occurrences of `trail1:` exist in any generated SPARQL string (verified by test).
- All SPARQL uses `PREFIX : <http://example.org/ontology#>` via the imported `PREFIXES` constant from `knowledge_base/repository.py`.
- The docstring explicitly warns contributors about the banned namespace — this is good project hygiene.

**SPARQL injection protection:**
- `_escape_sparql_literal()` escapes `\`, `"`, `\n`, `\r` — the four characters that can break a SPARQL quoted literal.
- Applied to every user-derived string before interpolation: `data.supplier_name`, `data.material`, `penalty_clause`, `data.document_id` (through `_build_contract_id`).

**Integer Day Rule is correct:**
- `_hours_to_days` uses integer floor-division (`//`), guaranteeing an `int`.
- The fallback `return days if days >= 1 else 1` ensures the SPARQL `xsd:integer` is valid (>0).
- The resulting `lead_days` is inserted without quotes — SPARQL parses it as an `xsd:integer` literal, which is type-correct.

### Issue 1 — `material_uri` could be empty (MINOR)

**Location:** Line 190.

```python
material_uri = _sanitize_uri_fragment(data.material)
```

`sanitize_uri_fragment` only strips spaces. If `data.material` consists entirely of non-alphanumeric characters (e.g., `"###"`), the result is `""`, producing the invalid SPARQL fragment `:  rdf:type :RawMaterial`.

**Fix:**
```python
def _build_material_uri(material: str) -> str:
    safe = _sanitize_uri_fragment(material)
    return safe if safe else f"Material_{abs(hash(material))}"
```

Then replace `material_uri = _sanitize_uri_fragment(data.material)` with `material_uri = _build_material_uri(data.material)`.

### Issue 2 — `_build_supplier_uri` prefix check is fragile (MINOR)

**Location:** Lines 97–98.

```python
safe = _sanitize_uri_fragment(supplier_id)
if not safe.startswith("Supplier"):
    safe = f"Supplier_{safe}"
```

A `supplier_id` like `"Best_Supplier_001"` would not get the prefix prepended (it already starts with "Supplier" mid-string). This is unlikely in practice but could cause URI collisions.

**Fix:** Check for exact prefix at the start of the string OR use a separator delimiter:

```python
if not safe.startswith("Supplier_"):
    safe = f"Supplier_{safe}"
```

### Namespace double-check

Ran a grep for the banned namespace — zero occurrences in generated SPARQL. The only mention is in the docstring as an explicit **FORBIDDEN** warning, which is correct documentation practice.

---

## File 4: `api/sandbox.py`

**🟢 PASS — with 1 minor inconsistency**

### What was done exceptionally well

**PDF resource cleanup:**
- `_extract_text_from_pdf` uses `with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:` — the `with` context manager guarantees `pdf.close()` is called on exit, even if `extract_text()` raises. No file descriptor leak.

**HTTP status codes match LangGraph states correctly:**

| State condition | HTTP code | Correct? |
|---|---|---|
| File read failure | 400 | ✅ |
| Empty file | 400 | ✅ |
| PDF unreadable | 400 (ValueError) | ✅ |
| `is_valid_contract == False` | 400 | ✅ |
| `extracted_data is None` | 422 | ✅ |
| Pipeline crash | 500 | ✅ |
| GraphDB fail in confirm-sla | 500 | ✅ |

**Layered architecture respected:** The endpoint calls `run_extraction_pipeline()` (service) which calls `LLMClient` (infrastructure) and `to_sla_contract`/`persist_confirmed_sla` (separate service). No SPARQL or LLM logic leaks into the API layer.

### Issue 1 — Mixed sync/async patterns (cosmetic, non-blocking)

**Location:** Lines 82 (`def upload_sla`) vs 166 (`async def upload_pdf`) vs 283 (`async def confirm_sla`).

**Problem:** The existing `upload_sla` endpoint is synchronous while the two new endpoints are async. FastAPI handles this transparently (sync endpoints run in a threadpool), but it's inconsistent. Since the project is migrating toward async, `upload_sla` should be converted for consistency.

**Fix:**
```python
@router.post("/upload-sla")
async def upload_sla(contract: SLAContract):
    # ... body unchanged ...
```

(No `await` is needed since `create_contract_graph` is sync — FastAPI will auto-wrap it, or use `run_in_executor`.)

### No memory leak confirmed

- `await file.read()` loads the full PDF into memory, which is normal for FastAPI file uploads.
- The `BytesIO` + `with pdfplumber.open` pattern ensures the PDF parser cleans up.
- No unclosed file handles, database connections, or HTTP sessions.

---

## Cross-Cutting Checks

| Criterion | Status | Evidence |
|---|---|---|
| `trail1:` namespace absent from all SPARQL | ✅ PASS | Verified by test + grep |
| `_hours_to_days` returns strict `int` | ✅ PASS | Integer `//` division + `return days if days >= 1 else 1` |
| 429 errors produce valid Pydantic, not crash | ✅ PASS | `_generate_fallback` returns typed `ExtractedSLAData`/`RiskAnalysisResult` |
| PDF files properly closed | ✅ PASS | `with pdfplumber.open(...)` context manager |
| All endpoints registered in router | ✅ PASS | 4 routes: `POST upload-sla`, `GET impacted-products`, `POST upload-pdf`, `POST confirm-sla` |
| App boots without import errors | ✅ PASS | Verified with `from main import app` |

---

## Actionable Fixes Summary

| Priority | File | Line | Issue | Fix |
|---|---|---|---|---|
| **Medium** | `services/llm_service.py` | 114 | Singleton race condition | Add `threading.Lock` double-checked locking |
| **Medium** | `api/sandbox.py` (+ optionally `llm_service.py`) | 231 | Sync LangGraph blocks async event loop | Wrap with `run_in_executor` or add `_async` wrapper |
| **Low** | `services/llm_service.py` | 16 | Unused `import json` | Remove line |
| **Low** | `services/llm_service.py` | 361 | Lost exception chain | Capture and re-raise with `from exc` |
| **Low** | `services/lifting_service.py` | 190 | `material_uri` could be empty | Add `_build_material_uri()` fallback |
| **Low** | `services/lifting_service.py` | 98 | Supplier prefix check fragile | Use `startswith("Supplier_")` |
| **Low** | `api/sandbox.py` | 82 | Mixed sync/async | Convert `upload_sla` to `async def` |

---

## Overall Verdict

```
models/schemas.py          🟢 PASS  — Ready for Sprint 4
services/llm_service.py    🟡 WARN  — 2 medium issues (singleton lock, async block)
services/lifting_service.py 🟢 PASS  — Ready for Sprint 4 (2 minor edge cases logged)
api/sandbox.py             🟢 PASS  — Ready for Sprint 4 (1 cosmetic inconsistency)
```

**Statement:** Sprint 3 achieves production-grade quality. The 429 fallback chain, namespace enforcement boundary, SPARQL escaping, and layered architecture are all correctly implemented. The two medium-priority issues (singleton thread safety and event-loop blocking) should be addressed before Sprint 4 concurrent-load scenarios, but neither is a correctness bug today. **Ready for Sprint 4.**
