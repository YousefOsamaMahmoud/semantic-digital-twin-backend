# Data Science Integration Guide

## Converting Standalone LLM Scripts into the Backend

This document explains how four standalone data science scripts from `Data_Science_Team/Graduation-Project/src/` were adapted into the production FastAPI/LangGraph backend under `Graduation Project/`.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Script-by-Script Mapping](#2-script-by-script-mapping)
3. [Namespace Migration (trail1: → :)](#3-namespace-migration)
4. [LangGraph StateGraph Conversion Pattern](#4-langgraph-stategraph-conversion-pattern)
5. [LLMClient Singleton & Fallback Architecture](#5-llmclient-singleton--fallback-architecture)
6. [Thread-Safe Async Execution](#6-thread-safe-async-execution)
7. [Named Graph Separation Strategy](#7-named-graph-separation-strategy)
8. [Pipeline Topologies](#8-pipeline-topologies)
9. [Testing Strategy](#9-testing-strategy)

---

## 1. Overview

### Source Scripts

| File | Purpose | Lines |
|---|---|---|
| `SLA Extractor (Tool Use) v3.py` | PDF text → structured SLA parameters via LLM tool-calling, with self-correcting validation loop | ~250 |
| `impact_mitigation_agents_v3.py` | IoT telemetry → multi-agent risk analysis → manager alerts | ~400 |
| `chat_v2.py` | Natural-language questions → SPARQL queries → human-readable answers | ~294 |
| `data_loader.py` | Seed data injection into GraphDB using `trail1:` namespace | ~200 |

### Target Backend Files

| Backend File | Source | Key Adaptation |
|---|---|---|
| `services/llm_service.py` | SLA Extractor v3 | Replaced raw `ChatOpenAI` with `LLMClient` singleton; added `threading.Lock`; modular extraction pipeline |
| `services/lifting_service.py` | SLA Extractor v3 (SPARQL section) | Rewrote namespace from `trail1:` to `PREFIX : <http://example.org/ontology#>`; added `_escape_sparql_literal` |
| `services/risk_engine_service.py` | impact_mitigation_agents_v3 | Compacted 7-node graph into 3 focused nodes; added `run_in_executor` async wrapper |
| `services/chat_service.py` | chat_v2.py | Same 4-node topology with project namespace; schema fetcher uses `knowledge_base/connection.py` |
| `services/data_ingestion_service.py` | data_loader.py | (Not yet implemented — Sprint 5) |

### Cross-Cutting Changes Applied to All Scripts

1. Hardcoded API keys removed → `.env` via `LLMConfig`
2. Raw `ChatOpenAI` → `LLMClient.get_instance().invoke_structured/invoke_text`
3. Raw `SPARQLWrapper` → `graphdb.execute_sparql_select/execute_sparql_update`
4. `trail1:` → `PREFIX : <http://example.org/ontology#>`
5. Filesystem I/O → HTTP API parameters
6. Synchronous `graph.invoke()` → `loop.run_in_executor()` for async endpoints

---

## 2. Script-by-Script Mapping

### 2.1 SLA Extractor v3 → `services/llm_service.py` + `services/lifting_service.py`

**Original components in the data science script:**

```
ContractData (Pydantic)      →  ExtractedSLAData (models/schemas.py)
ExtractionState (TypedDict)  →  SLAExtractionState (llm_service.py)
document_guardrail_node      →  document_guardrail_node (lifts identical logic)
extraction_agent_node        →  extraction_agent_node (uses LLMClient instead of raw ChatOpenAI)
business_logic_validator_node→  business_logic_validator_node (same 5 rules)
database_injector_node       →  SemanticLifter.lift_extracted_data() (lifting_service.py)
check_validation_success     →  check_validation_success (identical)
build_extractor_agent        →  build_extraction_graph() (same topology)
```

**Key changes:**
- `ContractData` was renamed to `ExtractedSLAData` with added `supplier_name` and `material` fields for human readability
- The original script's SPARQL injection logic (lines 124-163) was moved to `lifting_service.py` and rewritten with the project namespace
- The injector node is no longer part of the LangGraph — persistence is deferred until the human-in-the-loop `POST /confirm-sla` endpoint

### 2.2 impact_mitigation_agents_v3 → `services/risk_engine_service.py`

**Original components:**

```
RiskPipelineState (TypedDict)  →  RiskEngineState (risk_engine_service.py)
RiskAnalysis (Pydantic)        →  RiskAnalysisResult (models/schemas.py)
7 LangGraph nodes              →  3 nodes (fetch_sla, analyze_risk, generate_alert)
Conditional router             →  _determine_alert_title() function
```

**Compaction rationale:**
- `iot_simulator` node was removed (API layer provides the `IoTTelemetryEvent`)
- `graphdb_injector` and `context_query` were merged into `fetch_sla_node` (single SPARQL SELECT)
- `router` and `alert_generator` were merged into `generate_alert_node` (the `_determine_alert_title` logic is a pure function, not a separate LangGraph node)
- `validator` was removed (the `ManagerAlert` is always produced; the `validated` field defaults to `False`)

### 2.3 chat_v2.py → `services/chat_service.py`

**Original components:**

```
ChatState (TypedDict)          →  ChatState (identical structure)
fetch_live_schema()            →  fetch_live_schema() (uses graphdb.execute_sparql_select)
guardrail_node                 →  guardrail_node (uses LLMClient)
generate_sparql_node           →  generate_sparql_node (prompts use PREFIX : instead of trail1:)
execute_sparql_node            →  execute_sparql_node (uses graphdb connection)
translate_results_node         →  translate_results_node (identical)
should_retry                   →  should_retry (identical)
build_chat_agent               →  build_chat_graph (identical topology)
```

**Key changes:**
- All SPARQL examples in prompts use `PREFIX : <http://example.org/ontology#>` instead of `trail1:`
- Schema extraction queries filter with `FILTER(STRSTARTS(STR(?entity), "http://example.org/ontology#"))`
- `_schema_cache` module-level variable prevents repeated GraphDB queries
- `run_chat_pipeline_async` dispatches to thread pool for non-blocking FastAPI usage

---

## 3. Namespace Migration

### The Problem

Every data science script hardcodes the namespace:

```sparql
PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
```

The backend ontology uses:

```sparql
PREFIX : <http://example.org/ontology#>
```

### Migration Strategy

**Single chokepoint:** `services/lifting_service.py` is the exclusive module that generates SPARQL INSERT statements. All queries use `PREFIXES` imported from `knowledge_base/repository.py`:

```python
PREFIXES = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
```

**Guardrail test in test suite:** `test_lifter_namespace` asserts every generated SPARQL string:
- Contains `PREFIX : <http://example.org/ontology#>`
- Does NOT contain `trail1:`

**For SPARQL generation in chat_service.py:** The LLM system prompt explicitly instructs the model to use `PREFIX : <http://example.org/ontology#>` and the schema fetcher replaces the full URI with the `:` prefix:

```python
entity_name = row["entity"].replace("http://example.org/ontology#", ":")
```

---

## 4. LangGraph StateGraph Conversion Pattern

Every data science LangGraph was converted using the same pattern:

### Step 1: TypedDict → TypedDict (with Optional fields)

```python
# Original (data science)
class ExtractionState(TypedDict):
    raw_document_text: str
    extracted_data: Optional[ContractData]  # uses direct Pydantic import
    iteration_count: int

# Backend version
class SLAExtractionState(TypedDict):
    raw_document_text: str
    extracted_data: Optional[ExtractedSLAData]  # from models/schemas.py
    iteration_count: int
    # ... plus document_id, is_valid_contract, error_message, rdf_triples, injection_success
```

### Step 2: Node function signature unchanged

```python
def document_guardrail_node(state: SLAExtractionState) -> SLAExtractionState:
    # Body adapted to use LLMClient instead of raw llm.invoke()
```

### Step 3: Conditional router unchanged

```python
def check_validation_success(state: SLAExtractionState) -> str:
    if state["error_message"] and state["iteration_count"] < 3:
        return "retry_extraction"
    return "inject"
```

### Step 4: Graph builder adapted to use project types

```python
def build_extraction_graph() -> StateGraph:
    workflow = StateGraph(SLAExtractionState)
    workflow.add_node("guardrail", document_guardrail_node)
    workflow.add_node("extractor", extraction_agent_node)
    workflow.add_node("validator", business_logic_validator_node)
    workflow.set_entry_point("guardrail")
    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "extractor" if state["is_valid_contract"] else END,
    )
    workflow.add_edge("extractor", "validator")
    workflow.add_conditional_edges(
        "validator",
        check_validation_success,
        {"retry_extraction": "extractor", "inject": END},
    )
    return workflow.compile()
```

### Step 5: Public entry point

Synchronous:
```python
def run_extraction_pipeline(raw_text: str) -> dict[str, Any]:
    graph = build_extraction_graph()
    initial_state = _make_initial_state(raw_text)
    return graph.invoke(initial_state)
```

Async (for FastAPI):
```python
async def run_extraction_pipeline_async(raw_text: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_extraction_pipeline, raw_text)
```

---

## 5. LLMClient Singleton & Fallback Architecture

### 5.1 Singleton Pattern with Thread Safety

```python
class LLMClient:
    _instance: Optional["LLMClient"] = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls, config=None) -> "LLMClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance
```

The double-checked locking pattern prevents race conditions when multiple FastAPI workers hit `get_instance()` simultaneously on first access.

### 5.2 Fallback Chain

Every LLM call follows this priority:

1. **Attempt 1:** Primary LLM call via `ChatOpenAI`
2. **On 429/Quota:** Log warning → return deterministic `_generate_fallback(schema, input_vars)`
3. **On other error:** Retry up to `max_retries` (default 2) times with `retry_delay_ms` delay
4. **All retries exhausted:** Return fallback or re-raise depending on `fallback_enabled` flag

**Deterministic fallback responses:**

| Schema | Key Fallback Values |
|---|---|
| `ExtractedSLAData` | supplier_id="unknown", sla_lead_time_hours=72, delay_penalty_rate=500.0 |
| `RiskAnalysisResult` | risks=["DelayEvent"], confidence=0.5, severity="Low" |
| Free text (guardrail, SPARQL, alerts) | `"[Fallback Response] ..."` |

### 5.3 Guardrail Integration

The guardrail node detects fallback mode via the `[FALLBACK RESPONSE]` prefix:

```python
FALLBACK_MARKER = "[FALLBACK RESPONSE]"
if response.startswith(FALLBACK_MARKER):
    state["is_valid_contract"] = True  # Accept document for end-to-end testing
```

This ensures the entire pipeline can be tested without a live API key.

### 5.4 All Services Share One Client

```
llm_service.py          → LLMClient.get_instance().invoke_structured(...)
risk_engine_service.py  → LLMClient.get_instance().invoke_structured(...)
chat_service.py         → LLMClient.get_instance().invoke_text(...)
```

No module creates its own `ChatOpenAI` instance. Configuration is centralized in `LLMConfig` which reads from `.env`.

---

## 6. Thread-Safe Async Execution

### The Problem

LangGraph's `graph.invoke()` is synchronous and blocking. Running it inside a FastAPI `async def` endpoint blocks the event loop.

### The Solution

Each service provides two entry points:

```python
# Synchronous (for unit tests, CLI, background tasks)
def run_extraction_pipeline(raw_text: str) -> dict[str, Any]:
    graph = build_extraction_graph()
    return graph.invoke(_make_initial_state(raw_text))

# Async (for FastAPI endpoints)
async def run_extraction_pipeline_async(raw_text: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_extraction_pipeline, raw_text)
```

The async wrapper dispatches the synchronous `graph.invoke()` to a default thread pool executor, allowing the asyncio event loop to continue serving other requests.

### Where It's Applied

| Service | Sync Entry Point | Async Entry Point |
|---|---|---|
| `llm_service.py` | `run_extraction_pipeline` | Uses `run_in_executor` in `api/sandbox.py:upload_pdf` |
| `risk_engine_service.py` | (internal) | `process_iot_event` (async natively) |
| `chat_service.py` | `run_chat_pipeline` | `run_chat_pipeline_async` |

---

## 7. Named Graph Separation Strategy

GraphDB named graphs are used to separate ontology axioms from instance data:

| Named Graph URI | Content | Source |
|---|---|---|
| `http://example.org/ontology/` | OWL ontology (classes, properties, SWRL rules) | External `.owl` file loaded via GraphDB Workbench |
| `http://example.org/contracts/` | SLA contract instances (Supplier, RawMaterial, SLAContract) | `POST /confirm-sla` → `repository.create_contract_graph()` |

This separation ensures that ontology changes don't accidentally clobber production contract data, and that instance data can be backed up/exported independently.

---

## 8. Pipeline Topologies

### Topology A — SLA Extractor

```
                ENTRY
                  |
                  v
            [guardrail]
                  |
       +----------+-----------+
       | (INVALID)           | (VALID)
       v                      v
      END                 [extractor]
                              |
                              v
                         [validator]
                              |
                +-------------+-------------+
                | (error & <3)            | (success)
                v                          v
           [extractor]                   END
                                   (data returned to API
                                    for human review)
```

**Service file:** `services/llm_service.py`
**Entry point:** `run_extraction_pipeline(raw_text)`

### Topology B — Risk Engine

```
       ENTRY (IoTTelemetryEvent)
                  |
                  v
           [fetch_sla]
          (GraphDB query
         + mock fallback)
                  |
                  v
         [analyze_risk]
        (LLM structured
        risk assessment)
                  |
                  v
        [generate_alert]
       (role routing + text
         formatting)
                  |
                  v
                ManagerAlert
```

**Service file:** `services/risk_engine_service.py`
**Entry point:** `process_iot_event(event)`

### Topology C — SPARQL Chat Agent

```
                ENTRY (user question)
                  |
                  v
            [guardrail]
                  |
     +------------+-------------+
     | (off-topic)             | (valid)
     v                          v
[customer_service]        [developer]
     |                  (NL → SPARQL)
     |                        |
     |                        v
     |                   [database]
     |                   (GraphDB SELECT)
     |                        |
     |              +---------+----------+
     |              | (error & <3)      | (success)
     |              v                   v
     |         [developer]      [customer_service]
     |              |           (SPARQL → NL)
     +------+-------+                  |
            |                          v
            +---------->--------------END
```

**Service file:** `services/chat_service.py`
**Entry point:** `run_chat_pipeline(question)` / `run_chat_pipeline_async(question)`

---

## 9. Testing Strategy

### Test Suites

| Test File | Coverage | External Dependencies |
|---|---|---|
| `tests/test_graphdb_connection.py` | 3 tests: connection, triple insert, OWL inference | GraphDB |
| `tests/test_integration.py` | 14 tests / 70 assertions: models, singleton, fallback, topologies, namespace, escaping, URI, endpoint wiring | None (runs in CI) |

### What Integration Tests Verify

1. **Model imports** — All 6 Pydantic schemas instantiate correctly
2. **Singleton lock** — `LLMClient._lock` exists and `get_instance()` returns same object
3. **Fallback generation** — Every fallback schema produces valid, type-correct Pydantic instances
4. **Pipeline topology** — All 3 LangGraph graphs compile with the correct nodes registered
5. **Namespace enforcement** — `trail1:` is absent from all generated SPARQL
6. **Integer Day Rule** — `hours // 24` floor to 1 produces correct integers
7. **SPARQL escaping** — Quotes, backslashes, and newlines are properly escaped
8. **URI builders** — Supplier, material, and contract ID helpers handle edge cases
9. **Endpoint wiring** — All 9 API routes (5 sandbox + 4 dashboard) are registered

### Running Tests

```bash
# Integration tests (no dependencies)
python -m tests.test_integration
# Expected: 70/70 passed

# GraphDB tests (requires running database)
python -m tests.test_graphdb_connection
```
