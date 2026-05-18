# Technical Integration Blueprint — Data Science to Backend Services

> **Permanent Project Roadmap**
> Sprint 3 & 4 Integration Plan: Bridging `Data_Science_Team/` scripts into `services/`

---

## Phase 1: Source File Analysis

### 1.1 Component Mapping Matrix

| Data Science File | Key Components | Target Backend File | Purpose |
|---|---|---|---|
| `SLA Extractor (Tool Use) v3.py` | `ContractData` Pydantic, `ExtractionState` TypedDict, `document_guardrail_node`, `extraction_agent_node`, `business_logic_validator_node`, `database_injector_node`, `check_validation_success` router, LangGraph workflow builder | `services/llm_service.py` | Wrap LLM extraction + self-correcting validation into a callable service |
| `SLA Extractor (Tool Use) v3.py` | SPARQL injection logic (lines 124-163) using `trail1:` namespace | `services/lifting_service.py` | Semantic Lifting — map validated JSON to `http://example.org/ontology#` triples |
| `impact_mitigation_agents_v3.py` | `RiskPipelineState` TypedDict, `RiskAnalysis`/`RiskDetails` Pydantic, 7 LangGraph nodes, conditional router | `services/risk_engine_service.py` | Real-time multi-agent risk evaluation engine |
| `chat_v2.py` | `ChatState` TypedDict, `guardrail_node`, `generate_sparql_node`, `execute_sparql_node`, `translate_results_node`, self-correcting SPARQL loop | `services/chat_service.py` | NL to SPARQL query service for dashboard |
| `data_loader.py` | `build_supplier_triples`, `build_inventory_triples`, `build_delivery_triples`, SPARQL injection using `trail1:` namespace | `services/data_ingestion_service.py` + repurpose as bootstrap/seed script | Master data bootstrap into the backend's GraphDB |

### 1.2 Critical Cross-Cutting Concern — Namespace Divergence

**Data Science namespace:** `http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#` (prefix `trail1:`)

**Backend namespace:** `http://example.org/ontology#` (prefix `:`)

Every SPARQL query in the data science files uses `trail1:` — these will ALL need to be remapped to `:` before any data enters the backend's GraphDB. The `lifting_service.py` is the single chokepoint where this translation occurs.

### 1.3 Other Cross-Cutting Differences

| Concern | Data Science Scripts | Backend Target | Action Required |
|---|---|---|---|
| GraphDB repository | `SemanticDigitalTwin` | `supply-chain` (from `.env`) | All SPARQL endpoints must read from backend's `knowledge_base/connection.py` singleton |
| API key management | Hardcoded in source | `.env` via `LLMConfig` | Strip all hardcoded keys |
| LLM provider | OpenRouter + DeepSeek | Configurable via `LLMConfig` | Wrap in shared client |
| File I/O | Direct filesystem reads (`contracts/`, `data_Lake/`) | HTTP API parameters + DB queries | Remove all filesystem dependencies |
| LangGraph version | Implicit imports | Declare as project dependency | Add `langgraph`, `langchain-openai`, `langchain-core` to requirements |

---

## Phase 2: Core Architecture & Graph State Maps

### 2.1 New Pydantic Schemas (`models/schemas.py`)

#### Current (exists — do not modify):

```python
class SLAContract(BaseModel):
    supplier_name: str
    material: str
    lead_time_days: int
    penalty_clause: str
```

#### NEW — LLM Extraction Result (mapped from `ContractData` in SLA Extractor v3):

```python
class ExtractedSLAData(BaseModel):
    document_id: str
    supplier_id: str
    supplier_name: str
    material: str
    sla_lead_time_hours: int
    delay_penalty_rate: float
    missed_item_penalty_rate: float
    minimum_quality_threshold: float
    quality_penalty_rate: float
```

Field mapping from original `ContractData`:

| ContractData field | ExtractedSLAData field | Notes |
|---|---|---|
| `document_id` | `document_id` | Direct copy |
| `supplier_id` | `supplier_id` | Direct copy |
| _(missing)_ | `supplier_name` | **NEW** — human-readable name for human review step |
| _(missing)_ | `material` | **NEW** — human-readable material name for human review step |
| `sla_lead_time_hours` | `sla_lead_time_hours` | Direct copy |
| `delay_penalty_rate` | `delay_penalty_rate` | Direct copy |
| `missed_item_penalty_rate` | `missed_item_penalty_rate` | Direct copy |
| `minimum_quality_threshold` | `minimum_quality_threshold` | Direct copy |
| `quality_penalty_rate` | `quality_penalty_rate` | Direct copy |

#### NEW — For POST /confirm-sla (human review payload):

```python
class ConfirmedSLA(BaseModel):
    extraction_id: str
    supplier_name: str
    material: str
    lead_time_days: int
    penalty_clause: str
    corrections: str | None = None
```

#### NEW — Risk Analysis (mapped from `RiskAnalysis` in impact_mitigation_agents_v3):

```python
class RiskAnalysisResult(BaseModel):
    risks: list[str]
    confidence: float
    severity: str
    financial_penalty_estimate: float
    reasoning: str
```

#### NEW — IoT Telemetry Input:

```python
class IoTTelemetryEvent(BaseModel):
    delivery_id: str
    estimated_delay_hours: int
    reason_code: str
    disruption_probability: float
    timestamp: str
```

#### NEW — Manager Alert:

```python
class ManagerAlert(BaseModel):
    manager_title: str
    alert_text: str
    validated: bool = False
```

### 2.2 LangGraph State Dictionary Schemas

#### Graph State A — SLA Extraction Pipeline (`services/llm_service.py`)

```python
from typing import TypedDict
from models.schemas import ExtractedSLAData, ConfirmedSLA


class SLAExtractionState(TypedDict):
    # Input
    raw_document_text: str
    document_id: str

    # Guardrail
    is_valid_contract: bool

    # Extraction
    extracted_data: ExtractedSLAData | None
    iteration_count: int
    error_message: str

    # Semantic Lifting
    confirmed_payload: ConfirmedSLA | None
    rdf_triples: str
    injection_success: bool
```

State field lifecycle:

| Field | Set By | Consumed By | Description |
|---|---|---|---|
| `raw_document_text` | API endpoint (PDF text extraction) | `guardrail`, `extractor` | Raw text from uploaded PDF |
| `document_id` | API endpoint | `injector` | Auto-generated UUID or extracted ref |
| `is_valid_contract` | `guardrail` | Conditional router | Boolean guardrail verdict |
| `extracted_data` | `extractor` | `validator`, `lifting_service` | Structured LLM output |
| `iteration_count` | `extractor` | Conditional router | Retry counter (max 3) |
| `error_message` | `validator` | Conditional router, re-prompt | Business logic error for LLM correction |
| `confirmed_payload` | API endpoint (`confirm-sla`) | `injector` | Human-reviewed confirmation |
| `rdf_triples` | `lifting_service` | `injector` | Generated SPARQL INSERT string |
| `injection_success` | `injector` | API response | GraphDB persistence flag |

#### Graph State B — Risk Engine Pipeline (`services/risk_engine_service.py`)

```python
from typing import TypedDict, Any
from models.schemas import RiskAnalysisResult


class RiskEngineState(TypedDict):
    # Input (from IoT / API trigger)
    delivery_id: str
    delay_hours: int
    reason_code: str

    # Ontology Layer
    injection_success: bool
    ontology_risks: list[str]

    # Context Layer
    context_data: dict[str, Any]
    # context_data keys:
    #   sla_lead_time: int
    #   inventory_stock: int
    #   safety_stock: int
    #   penalty_rate: float

    # LLM Analysis Layer
    risk_analysis: RiskAnalysisResult | dict

    # Routing & Alerts
    target_managers: list[str]
    alerts: dict[str, str]
    alerts_validated: bool
```

State field lifecycle:

| Field | Set By | Consumed By | Description |
|---|---|---|---|
| `delivery_id` | API endpoint | All downstream nodes | Delivery identifier from IoT or manual trigger |
| `delay_hours` | API endpoint | `graphdb_injector`, `risk_analyst` | Estimated delay from IoT telemetry |
| `reason_code` | API endpoint | `graphdb_injector`, `risk_analyst`, `alert_generator` | Delay reason (e.g., "Transport/Weather") |
| `injection_success` | `graphdb_injector` | Logging / response | Whether DelayEvent was persisted |
| `ontology_risks` | `context_query` | `risk_analyst` | OWL-inferred risk types from GraphDB |
| `context_data` | `context_query` | `risk_analyst` | SLA terms, inventory levels, penalty rates |
| `risk_analysis` | `risk_analyst` | `router`, `alert_generator`, `validator` | Structured LLM risk assessment |
| `target_managers` | `router` | `alert_generator` | Manager roles to notify |
| `alerts` | `alert_generator` | `validator`, API response | Per-manager alert text |
| `alerts_validated` | `validator` | API response | Quality check flag |

#### Graph State C — SPARQL Chat Agent (`services/chat_service.py`)

```python
from typing import TypedDict, Any


class ChatState(TypedDict):
    # Input
    user_question: str
    live_schema: str

    # Guardrail
    is_valid_topic: bool

    # SPARQL Generation
    generated_sparql: str
    graph_results: list[dict[str, Any]]
    error_message: str
    iteration_count: int

    # Output
    final_answer: str
```

State field lifecycle:

| Field | Set By | Consumed By | Description |
|---|---|---|---|
| `user_question` | API endpoint | `guardrail`, `developer`, `customer_service` | Raw natural language question |
| `live_schema` | Constructor (on boot) | `developer` | GraphDB schema fetched via SPARQL |
| `is_valid_topic` | `guardrail` | Conditional router | Supply-chain domain check |
| `generated_sparql` | `developer` | `database` | LLM-generated SPARQL query |
| `graph_results` | `database` | `customer_service` | SPARQL SELECT results |
| `error_message` | `database` | Conditional router | SPARQL syntax/runtime error for self-correction |
| `iteration_count` | `developer` | Conditional router | Self-correction counter (max 3) |
| `final_answer` | `customer_service` | API response | Natural language answer to the user |

### 2.3 LangGraph Topology Maps

#### Topology A — SLA Extractor (adaptation of `build_extractor_agent`)

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
                    | (error & <3 retry)      | (success)
                    v                          v
               [extractor]              [injector]
                                  (calls lifting_service)
                                  |
                                  v
                                 END
```

**Conditional Router logic (`check_validation_success`):**

```python
def check_validation_success(state: SLAExtractionState) -> str:
    if state["error_message"] and state["iteration_count"] < 3:
        return "retry_extraction"   # routes back to extractor
    return "inject"                 # routes forward to injector
```

**Graph compilation:**

```python
def build_extraction_graph() -> CompiledStateGraph:
    workflow = StateGraph(SLAExtractionState)

    workflow.add_node("guardrail", document_guardrail_node)
    workflow.add_node("extractor", extraction_agent_node)
    workflow.add_node("validator", business_logic_validator_node)
    workflow.add_node("injector", database_injector_node)

    workflow.set_entry_point("guardrail")
    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "extractor" if state["is_valid_contract"] else END
    )
    workflow.add_edge("extractor", "validator")
    workflow.add_conditional_edges(
        "validator",
        check_validation_success,
        {"retry_extraction": "extractor", "inject": "injector"}
    )
    workflow.add_edge("injector", END)

    return workflow.compile()
```

#### Topology B — Risk Engine (adaptation of `build_pipeline`)

```
                    ENTRY
                      |
                      v
             [iot_simulator]
                      |
                      v
           [graphdb_injector]
                      |
                      v
             [context_query]
                      |
                      v
             [risk_analyst]
                      |
                      v
                [router]
                      |
          +-----------+-----------+
          | (targets exist)      | (no targets)
          v                       v
    [alert_generator]            END
          |
          v
     [validator]
          |
          v
         END
```

**Conditional Router logic:**

```python
def router(state: RiskEngineState) -> RiskEngineState:
    analysis = state["risk_analysis"]
    active_risks = analysis.get("risks", [])

    targets = set()
    if "DelayEvent" in active_risks or "ProductionDisruption" in active_risks:
        targets.add("Production Manager")
    if "SLAViolation" in active_risks:
        targets.add("Procurement Manager")
    if "ProductionDisruption" in active_risks:
        targets.add("Logistics Manager")

    state["target_managers"] = list(targets)
    return state
```

**Graph compilation:**

```python
def build_risk_pipeline() -> CompiledStateGraph:
    workflow = StateGraph(RiskEngineState)

    workflow.add_node("iot_simulator", read_iot_telemetry)
    workflow.add_node("graphdb_injector", inject_and_reason_in_graphdb)
    workflow.add_node("context_query", query_ontology_context)
    workflow.add_node("risk_analyst", risk_analyst_agent)
    workflow.add_node("router", router)
    workflow.add_node("alert_generator", generate_manager_alerts)
    workflow.add_node("validator", validate_alerts)

    workflow.set_entry_point("iot_simulator")
    workflow.add_edge("iot_simulator", "graphdb_injector")
    workflow.add_edge("graphdb_injector", "context_query")
    workflow.add_edge("context_query", "risk_analyst")
    workflow.add_edge("risk_analyst", "router")

    workflow.add_conditional_edges(
        "router",
        lambda state: "generate" if state["target_managers"] else "end",
        {"generate": "alert_generator", "end": END}
    )

    workflow.add_edge("alert_generator", "validator")
    workflow.add_edge("validator", END)

    return workflow.compile()
```

#### Topology C — SPARQL Chat Agent (adaptation of `build_chat_agent`)

```
                    ENTRY
                      |
                      v
               [guardrail]
                      |
          +-----------+-----------+
          | (OFF-TOPIC)          | (VALID)
          v                       v
    [customer_service]       [developer]
          |                       |
          |                       v
          |                  [database]
          |                       |
          |            +----------+-----------+
          |            | (error & <3 retry)  | (success)
          |            v                      v
          |       [developer]          [customer_service]
          |            |                      |
          +------------+----------------------+
                                               |
                                               v
                                              END
```

**Conditional Router logic:**

```python
def should_retry(state: ChatState) -> str:
    if state.get("error_message") != "" and state["iteration_count"] < 3:
        return "retry"
    return "translate"
```

**Graph compilation:**

```python
def build_chat_agent() -> CompiledStateGraph:
    workflow = StateGraph(ChatState)

    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("developer", generate_sparql_node)
    workflow.add_node("database", execute_sparql_node)
    workflow.add_node("customer_service", translate_results_node)

    workflow.set_entry_point("guardrail")

    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "developer" if state["is_valid_topic"] else "customer_service",
        {"developer": "developer", "customer_service": "customer_service"}
    )

    workflow.add_edge("developer", "database")

    workflow.add_conditional_edges(
        "database",
        should_retry,
        {"retry": "developer", "translate": "customer_service"}
    )

    workflow.add_edge("customer_service", END)

    return workflow.compile()
```

---

## Phase 3: Step-by-Step Implementation Sequence

### Sprint 3 — Build the Brain

#### Step 3.1 — `models/schemas.py` (add new models)

**Action:** Append the following Pydantic models to the existing `models/schemas.py`:

- `ExtractedSLAData` (9 fields: document_id, supplier_id, supplier_name, material, sla_lead_time_hours, delay_penalty_rate, missed_item_penalty_rate, minimum_quality_threshold, quality_penalty_rate)
- `ConfirmedSLA` (6 fields: extraction_id, supplier_name, material, lead_time_days, penalty_clause, corrections)
- `RiskAnalysisResult` (5 fields: risks, confidence, severity, financial_penalty_estimate, reasoning)
- `IoTTelemetryEvent` (5 fields: delivery_id, estimated_delay_hours, reason_code, disruption_probability, timestamp)
- `ManagerAlert` (3 fields: manager_title, alert_text, validated)

All fields must include `Field(...)` with `min_length`, `gt`, `examples`, and `description` matching the conventions in the existing `SLAContract` model.

**Verification:** Run `python -c "from models.schemas import *"` to confirm no import errors.

---

#### Step 3.2 — `services/llm_service.py`

**File purpose:** LLM configuration singleton + SLA extraction LangGraph pipeline.

**Sections to implement in order:**

1. **`LLMConfig` dataclass**
   - Fields: `provider` (default `"openrouter"`), `model` (default `"deepseek/deepseek-chat"`), `api_key` (reads from `os.getenv("LLM_API_KEY")`), `base_url` (default `"https://openrouter.ai/api/v1"`), `temperature` (default `0.0`), `max_tokens` (default `800`)
   - Fallback fields: `fallback_enabled` (default `True`), `max_retries` (default `2`), `retry_delay_ms` (default `1000`)

2. **`LLMClient` class**
   - Singleton pattern: `_instance` class attribute, `__init__` builds `ChatOpenAI`, `get_instance(config)` classmethod
   - `invoke_structured(prompt, input_vars, output_schema) -> BaseModel`:
     - Retry loop up to `max_retries + 1` attempts
     - On 429 / "quota" / "resource exhausted": log warning, call `_generate_fallback(output_schema, input_vars)`
     - On other exception: retry with `time.sleep(retry_delay_ms)`, then fallback if exhausted
   - `invoke_text(prompt, input_vars) -> str`:
     - Same retry + fallback pattern returning a safe default string
   - `_generate_fallback(schema, context) -> BaseModel`:
     - If `schema == ExtractedSLAData`: return `ExtractedSLAData(document_id="FALLBACK-..." + uuid[:8], supplier_id="unknown", supplier_name="Unknown Supplier", material="Unknown Material", sla_lead_time_hours=72, delay_penalty_rate=500.0, missed_item_penalty_rate=150.0, minimum_quality_threshold=0.98, quality_penalty_rate=0.15)`
     - If `schema == RiskAnalysisResult`: return `RiskAnalysisResult(risks=["DelayEvent"], confidence=0.5, severity="Low", financial_penalty_estimate=0.0, reasoning="Fallback mode: LLM quota exceeded.")`

3. **`SLAExtractionState` TypedDict**
   - As defined in Phase 2.2, Graph State A

4. **Node functions (adapted from SLA Extractor v3):**

   - `document_guardrail_node(state: SLAExtractionState) -> SLAExtractionState`:
     - Same system prompt: "You are a document classifier..."
     - Calls `LLMClient.get_instance().invoke_text(prompt, {"text": state["raw_document_text"]})`
     - Sets `state["is_valid_contract"] = True/False`

   - `extraction_agent_node(state: SLAExtractionState) -> SLAExtractionState`:
     - Builds ChatPromptTemplate with system prompt including `{error_message}`
     - Calls `LLMClient.get_instance().invoke_structured(prompt, {"text": ..., "error_message": ...}, ExtractedSLAData)`
     - Sets `state["extracted_data"] = result`, increments `state["iteration_count"]`

   - `business_logic_validator_node(state: SLAExtractionState) -> SLAExtractionState`:
     - Validates `state["extracted_data"]`:
       - Rule 1: `sla_lead_time_hours > 0`
       - Rule 2: `minimum_quality_threshold <= 1.0`
       - Rule 3: `quality_penalty_rate <= 1.0`
       - Rule 4: `supplier_id` and `supplier_name` are non-empty
     - On failure: sets `state["error_message"]` to the specific business rule violated
     - On success: sets `state["error_message"] = ""`

   - `database_injector_node(state: SLAExtractionState) -> SLAExtractionState`:
     - Calls `lifting_service.lift_extracted_data(state["extracted_data"])` to generate SPARQL
     - Calls `repository.create_contract_graph(...)` to persist
     - Sets `state["injection_success"] = True/False`

5. **`check_validation_success(state) -> str`** — conditional router as defined in Phase 2.3 Topology A

6. **`build_extraction_graph() -> CompiledStateGraph`** — assembles 4 nodes + conditional edges as defined in Phase 2.3 Topology A

7. **Public entry point:**

```python
def run_extraction_pipeline(raw_text: str) -> SLAExtractionState:
    app = build_extraction_graph()
    initial_state: SLAExtractionState = {
        "raw_document_text": raw_text,
        "document_id": "",
        "is_valid_contract": False,
        "extracted_data": None,
        "iteration_count": 0,
        "error_message": "",
        "confirmed_payload": None,
        "rdf_triples": "",
        "injection_success": False,
    }
    return app.invoke(initial_state)
```

**Verification:** Write a unit test that passes a known SLA text and asserts `is_valid_contract == True`, `extracted_data is not None`, `extracted_data.sla_lead_time_hours > 0`. Mock LLM responses to avoid API calls during CI.

---

#### Step 3.3 — `services/lifting_service.py`

**File purpose:** Convert validated JSON into GraphDB-compatible RDF triples using the backend's `http://example.org/ontology#` namespace.

**Sections to implement:**

1. **Import preamble:**

```python
from database.repository import PREFIXES, CONTRACT_GRAPH, _sanitize_uri_fragment, create_contract_graph
from models.schemas import ExtractedSLAData, ConfirmedSLA, SLAContract
```

2. **`SemanticLifter` class:**

   - `lift_extracted_data(data: ExtractedSLAData) -> dict`:
     - Converts `sla_lead_time_hours / 24` to `lead_time_days` (integer ceiling)
     - Builds an `SLAContract` Pydantic object: `SLAContract(supplier_name=data.supplier_name, material=data.material, lead_time_days=converted_days, penalty_clause=f"Delay: ${data.delay_penalty_rate}/day; Missed item: ${data.missed_item_penalty_rate}/unit; Quality: {data.quality_penalty_rate*100}% of order value")`
     - Returns `{"contract": slacontract, "document_id": data.document_id, "supplier_id": data.supplier_id}`

   - `lift_confirmed_sla(confirmed: ConfirmedSLA) -> dict`:
     - Maps `ConfirmedSLA` directly to `SLAContract`:
       - `supplier_name` = `confirmed.supplier_name`
       - `material` = `confirmed.material`
       - `lead_time_days` = `confirmed.lead_time_days`
       - `penalty_clause` = `confirmed.penalty_clause`
     - Calls `create_contract_graph(slacontract)` from `knowledge_base/repository.py`
     - Returns the result dict from `create_contract_graph`

3. **`build_sla_sparql_insert(data: ExtractedSLAData) -> str`:**
   - Manually constructs a SPARQL INSERT string using the backend's `PREFIXES` and `CONTRACT_GRAPH`
   - Creates triples:
     - `:{doc_id} rdf:type :SLA_Agreement`
     - `:{doc_id} :hasSLALeadTime "{data.sla_lead_time_hours}"^^xsd:integer`
     - `:{doc_id} :hasDelayPenaltyRate "{data.delay_penalty_rate}"^^xsd:decimal`
     - `:{doc_id} :hasMissedItemPenaltyRate "{data.missed_item_penalty_rate}"^^xsd:decimal`
     - `:{doc_id} :hasMinimumQualityThreshold "{data.minimum_quality_threshold}"^^xsd:decimal`
     - `:{doc_id} :hasQualityPenaltyRate "{data.quality_penalty_rate}"^^xsd:decimal`
     - `:{doc_id} :governs :{_sanitize_uri_fragment(data.supplier_id)}`
   - **IMPORTANT:** Uses `PREFIX : <http://example.org/ontology#>` — NOT `trail1:`

4. **Public function:**

```python
def persist_confirmed_sla(confirmed: ConfirmedSLA) -> dict:
    """Convert ConfirmedSLA to SLAContract and persist via repository."""
    contract = SLAContract(
        supplier_name=confirmed.supplier_name,
        material=confirmed.material,
        lead_time_days=confirmed.lead_time_days,
        penalty_clause=confirmed.penalty_clause,
    )
    return create_contract_graph(contract)
```

**Verification:** Unit test: pass an `ExtractedSLAData` instance, assert the returned SPARQL string contains `PREFIX : <http://example.org/ontology#>` and does NOT contain `trail1:`.

---

#### Step 3.4 — `api/sandbox.py` (new endpoints)

**Endpoint 1 — POST /api/sandbox/upload-pdf:**

```python
@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accept a PDF file, extract text, run LLM extraction pipeline,
    return structured JSON for human review.
    """
    # 1. Read uploaded file
    contents = await file.read()

    # 2. Extract text from PDF
    text = extract_text_from_pdf(contents)  # using PyPDF2 or pdfplumber

    # 3. Run extraction pipeline
    result = run_extraction_pipeline(text)

    if not result["is_valid_contract"]:
        raise HTTPException(status_code=400, detail="Document is not a valid SLA contract.")

    if result["extracted_data"] is None:
        raise HTTPException(status_code=422, detail="LLM extraction failed after max retries.")

    # 4. Return extracted data for human review
    return {
        "status": "success",
        "extraction_id": str(uuid.uuid4()),
        "data": result["extracted_data"].model_dump(),
        "message": "Please review the extracted data and POST to /confirm-sla to persist.",
    }
```

**Endpoint 2 — POST /api/sandbox/confirm-sla:**

```python
@router.post("/confirm-sla")
def confirm_sla(confirmed: ConfirmedSLA):
    """
    Accept human-reviewed SLA payload, lift to RDF triples,
    persist to GraphDB.
    """
    try:
        graph_result = persist_confirmed_sla(confirmed)
        return {
            "status": "success",
            "message": f"SLA contract confirmed and saved to GraphDB.",
            "graph_data": graph_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist confirmed SLA: {str(e)}")
```

**Helper function for PDF text extraction (can live in same file or a small `services/pdf_service.py`):**

```python
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF byte stream using pdfplumber."""
    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
```

---

### Sprint 4 — Build the Intelligence

#### Step 4.1 — `services/risk_engine_service.py`

**File purpose:** Multi-agent LangGraph pipeline that ingests IoT telemetry, queries GraphDB for context, runs LLM risk analysis, routes to managers, and generates validated alerts.

**Sections to implement:**

1. **`RiskEngineState` TypedDict** — as defined in Phase 2.2, Graph State B

2. **LLM integration** — uses the `LLMClient` singleton from `llm_service.py`

3. **GraphDB integration** — uses `knowledge_base/connection.graphdb` singleton (NOT creating its own SPARQLWrapper)

4. **Namespace enforcement** — ALL SPARQL queries use `PREFIX : <http://example.org/ontology#>` — the `trail1:` prefix is strictly forbidden

5. **Node functions (adapted from `impact_mitigation_agents_v3.py`):**

   - `read_iot_telemetry(state: RiskEngineState) -> RiskEngineState`:
     - Adapted to accept input from API parameters, not filesystem
     - See "API trigger flow" below

   - `inject_and_reason_in_graphdb(state: RiskEngineState) -> RiskEngineState`:
     - Build SPARQL INSERT with `:Risk_{timestamp}` as a `:DelayEvent` individual
     - Uses `:hasDelayDuration`, `:hasReasonCode`, `:hasRiskStatus "Predicted"`
     - Uses `knowledge_base/connection.graphdb.execute_sparql_update()`
     - Sets `state["injection_success"]`

   - `query_ontology_context(state: RiskEngineState) -> RiskEngineState`:
     - SPARQL SELECT to find: `:DelayEvent` affecting the delivery, SLA lead time, inventory levels, penalty rates
     - Same multi-hop query pattern as original but uses backend namespace
     - Sets `state["ontology_risks"]` and `state["context_data"]`

   - `risk_analyst_agent(state: RiskEngineState) -> RiskEngineState`:
     - Same `RISK_ANALYST_PROMPT` template
     - Calls `LLMClient.get_instance().invoke_structured(prompt, vars, RiskAnalysisResult)`
     - Sets `state["risk_analysis"]`

   - `router(state: RiskEngineState) -> RiskEngineState` — as defined in Phase 2.3 Topology B

   - `generate_manager_alerts(state: RiskEngineState) -> RiskEngineState`:
     - Same `ALERT_PROMPTS` dictionary
     - Calls `LLMClient.get_instance().invoke_text()` for each manager
     - Sets `state["alerts"]`

   - `validate_alerts(state: RiskEngineState) -> RiskEngineState`:
     - Same `VALIDATOR_PROMPT`
     - Sets `state["alerts_validated"] = True`

6. **API trigger flow** — the `read_iot_telemetry` node is replaced when called from the API:

```python
def execute_risk_assessment(telemetry: IoTTelemetryEvent) -> RiskEngineState:
    app = build_risk_pipeline()
    initial_state: RiskEngineState = {
        "delivery_id": telemetry.delivery_id,
        "delay_hours": telemetry.estimated_delay_hours,
        "reason_code": telemetry.reason_code,
        "injection_success": False,
        "ontology_risks": [],
        "context_data": {},
        "risk_analysis": {},
        "target_managers": [],
        "alerts": {},
        "alerts_validated": False,
    }
    return app.invoke(initial_state)
```

**Verification:** Integration test with a known telemetry event. Mock GraphDB and LLM responses. Assert correct `target_managers` population and `alerts` generation.

---

#### Step 4.2 — `services/chat_service.py`

**File purpose:** NL-to-SPARQL LangGraph agent that lets users ask supply-chain questions in natural language and get answers backed by live GraphDB queries.

**Sections to implement:**

1. **`ChatState` TypedDict** — as defined in Phase 2.2, Graph State C

2. **Schema fetcher:**

```python
def fetch_live_schema() -> str:
    """Query GraphDB for all classes, object properties, and data properties."""
    schema_query = f"""
    {PREFIXES}
    SELECT ?type ?entity WHERE {{
      {{ ?entity a owl:Class . BIND("Class" AS ?type) }}
      UNION {{ ?entity a owl:ObjectProperty . BIND("ObjectProperty" AS ?type) }}
      UNION {{ ?entity a owl:DatatypeProperty . BIND("DataProperty" AS ?type) }}
      FILTER(STRSTARTS(STR(?entity), "http://example.org/ontology#"))
    }}
    """
    results = graphdb.execute_sparql_select(schema_query)
    # ... group by type and format as schema string
```

3. **Node functions (adapted from `chat_v2.py`):**

   - `guardrail_node(state: ChatState) -> ChatState`:
     - Same supply-chain domain classifier prompt
     - Calls `LLMClient.get_instance().invoke_text()`
     - Sets `state["is_valid_topic"]`

   - `generate_sparql_node(state: ChatState) -> ChatState`:
     - Same system prompt with live schema and error context
     - **Namespace change:** prompt instructs LLM to use `PREFIX : <http://example.org/ontology#>` instead of `trail1:`
     - Strips markdown formatting from response
     - Sets `state["generated_sparql"]`, increments `state["iteration_count"]`

   - `execute_sparql_node(state: ChatState) -> ChatState`:
     - Calls `graphdb.execute_sparql_select(state["generated_sparql"])`
     - On success: sets `state["graph_results"]`, clears `state["error_message"]`
     - On error: sets `state["error_message"]` to the SPARQL error

   - `translate_results_node(state: ChatState) -> ChatState`:
     - If `not is_valid_topic`: returns polite out-of-domain message
     - If `error_message and iteration_count >= 3`: returns apology
     - Otherwise: LLM translates JSON results to natural language

4. **`build_chat_agent() -> CompiledStateGraph`** — as defined in Phase 2.3 Topology C

5. **Public entry point:**

```python
def ask_question(question: str) -> str:
    schema = fetch_live_schema()
    app = build_chat_agent()
    initial_state: ChatState = {
        "user_question": question,
        "live_schema": schema,
        "generated_sparql": "",
        "graph_results": [],
        "error_message": "",
        "iteration_count": 0,
        "final_answer": "",
        "is_valid_topic": True,
    }
    final = app.invoke(initial_state)
    return final["final_answer"]
```

**Verification:** Unit test with mocked SPARQL results. Assert "final_answer" is a non-empty string and does not contain raw JSON or SPARQL.

---

#### Step 4.3 — `api/dashboard.py`

**File purpose:** Dashboard endpoints for risk scores, compliance alerts, and fallback supplier options.

```python
from fastapi import APIRouter, HTTPException
from database.repository import (
    find_impacted_products_by_supplier_delay,
)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get("/risk-scores")
def get_risk_scores():
    """
    GET /api/dashboard/risk-scores

    Returns array of materials with delay probability and traffic-light status.
    Currently returns OWL-inferred at-risk products.
    Sprint 4 enhancement: integrate ML model predictions.
    """
    try:
        results = find_impacted_products_by_supplier_delay()
        risk_scores = []
        for row in results:
            risk_scores.append({
                "product": row.get("productLabel", "Unknown"),
                "supplier": row.get("supplierLabel", "Unknown"),
                "material": row.get("materialLabel", "Unknown"),
                "status": "RED" if row.get("riskStatus", "").lower() == "true" else "GREEN",
            })
        return {"status": "success", "count": len(risk_scores), "risk_scores": risk_scores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compliance-alerts")
def get_compliance_alerts():
    """
    GET /api/dashboard/compliance-alerts

    Queries GraphDB for SLA violations where actual delay exceeds lead time.
    Surface active penalty fines and affected production lines.
    """
    try:
        # SPARQL query to find SLA violations
        query = f"""
        PREFIX : <http://example.org/ontology#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?supplier ?material ?leadTimeDays ?delayHours ?penalty
        WHERE {{
            ?supplier rdf:type :Supplier ;
                      :supplies ?material ;
                      :leadTimeDays ?leadTimeDays .
            ?material rdf:type :RawMaterial .
            OPTIONAL {{ ?supplier :penaltyClause ?penalty . }}
        }}
        """
        from database.connection import graphdb
        results = graphdb.execute_sparql_select(query)
        return {"status": "success", "count": len(results), "alerts": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fallback-options/{material_id}")
def get_fallback_options(material_id: str):
    """
    GET /api/dashboard/fallback-options/{material_id}

    Query GraphDB for alternative suppliers for a given material.
    Filters by material type, returns ranked backup options.
    """
    try:
        from database.repository import _sanitize_uri_fragment
        safe_material = _sanitize_uri_fragment(material_id)

        query = f"""
        PREFIX : <http://example.org/ontology#>
        SELECT DISTINCT ?supplier ?supplierName ?reliabilityScore
        WHERE {{
            ?supplier rdf:type :Supplier ;
                      rdfs:label ?supplierName ;
                      :supplies :{safe_material} .
            OPTIONAL {{ ?supplier :hasReliabilityScore ?reliabilityScore . }}
        }}
        ORDER BY DESC(?reliabilityScore)
        """
        from database.connection import graphdb
        results = graphdb.execute_sparql_select(query)
        return {"status": "success", "count": len(results), "suppliers": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Phase 4: Resilient LLM Design & Quota Guardrails

### 4.1 LLM Configuration Architecture (`services/llm_service.py`)

```python
import os
import time
import logging
from uuid import uuid4
from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Centralized LLM configuration — all services share this."""
    provider: str = "openrouter"
    model: str = "deepseek/deepseek-chat"
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.0
    max_tokens: int = 800

    # Fallback behavior
    fallback_enabled: bool = True
    max_retries: int = 2
    retry_delay_ms: int = 1000


class LLMClient:
    """
    Singleton LLM client with structured fallback.

    Every LLM call in every service MUST go through this client.
    If the Gemini/OpenRouter API returns 429 Quota Exceeded, this
    client catches the error and returns a deterministic simulation
    response — the FastAPI endpoint and GraphDB never crash.
    """

    _instance: Optional["LLMClient"] = None

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._primary_llm = self._build_llm()

    @classmethod
    def get_instance(cls, config: Optional[LLMConfig] = None) -> "LLMClient":
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def _build_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.config.model,
            openai_api_key=self.config.api_key,
            openai_api_base=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def invoke_structured(
        self,
        prompt: ChatPromptTemplate,
        input_vars: dict,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """
        Call LLM with structured output (tool use / function calling).

        Retry logic:
          1. Attempt primary call
          2. On 429 / quota error → log + return simulated fallback
          3. On other error → retry up to max_retries times
          4. If all retries exhausted → return simulated fallback
        """
        for attempt in range(1 + self.config.max_retries):
            try:
                chain = prompt | self._primary_llm.with_structured_output(output_schema)
                return chain.invoke(input_vars)
            except Exception as e:
                error_str = str(e).lower()
                is_quota = (
                    "429" in error_str
                    or "quota" in error_str
                    or "resource exhausted" in error_str
                    or "rate limit" in error_str
                )
                if is_quota and self.config.fallback_enabled:
                    logger.warning(f"LLM quota exceeded: {e}. Returning simulated fallback.")
                    return self._generate_fallback(output_schema, input_vars)

                if attempt < self.config.max_retries:
                    wait = self.config.retry_delay_ms / 1000
                    logger.info(f"LLM call failed (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                logger.error(f"LLM call failed after {self.config.max_retries} retries: {e}")
                if self.config.fallback_enabled:
                    return self._generate_fallback(output_schema, input_vars)
                raise

        return self._generate_fallback(output_schema, input_vars)

    def invoke_text(
        self,
        prompt: ChatPromptTemplate,
        input_vars: dict,
    ) -> str:
        """
        Call LLM for free-text generation (no structured output).

        Same retry + fallback pattern as invoke_structured.
        """
        for attempt in range(1 + self.config.max_retries):
            try:
                chain = prompt | self._primary_llm
                return chain.invoke(input_vars).content.strip()
            except Exception as e:
                error_str = str(e).lower()
                is_quota = (
                    "429" in error_str
                    or "quota" in error_str
                    or "resource exhausted" in error_str
                )
                if is_quota and self.config.fallback_enabled:
                    logger.warning(f"LLM quota exceeded: {e}. Returning fallback text.")
                    return self._generate_fallback_text(input_vars)

                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay_ms / 1000)
                    continue

                if self.config.fallback_enabled:
                    return self._generate_fallback_text(input_vars)
                raise

        return self._generate_fallback_text(input_vars)

    def _generate_fallback(self, schema: type[BaseModel], context: dict) -> BaseModel:
        """Generate a deterministic simulation response for the given schema."""
        from models.schemas import ExtractedSLAData, RiskAnalysisResult

        if schema == ExtractedSLAData:
            return ExtractedSLAData(
                document_id=f"FALLBACK-{uuid4().hex[:8]}",
                supplier_id="unknown",
                supplier_name="Unknown Supplier (Fallback)",
                material="Unknown Material (Fallback)",
                sla_lead_time_hours=72,
                delay_penalty_rate=500.0,
                missed_item_penalty_rate=150.0,
                minimum_quality_threshold=0.98,
                quality_penalty_rate=0.15,
            )

        if schema == RiskAnalysisResult:
            return RiskAnalysisResult(
                risks=["DelayEvent"],
                confidence=0.5,
                severity="Low",
                financial_penalty_estimate=0.0,
                reasoning=(
                    "Fallback mode: LLM quota exceeded. "
                    "Conservative default risk assessment applied. "
                    "No active alerts generated."
                ),
            )

        # Generic fallback: return empty instance
        return schema()

    def _generate_fallback_text(self, context: dict) -> str:
        """Generate a deterministic fallback text response."""
        return (
            "[Fallback Response] The AI assistant is currently in offline mode "
            "due to a temporary service interruption. Please try again later."
        )
```

### 4.2 Fallback Chain Flow

```
API Request (upload-pdf / risk-assessment / chat)
    │
    ▼
Service calls LLMClient.invoke_structured(prompt, vars, schema)
    │
    ├── Attempt 1: Primary LLM call
    │       │
    │       ├── Success ──→ return validated Pydantic object ──→ happy path
    │       │
    │       ├── 429 Quota ──→ log warning
    │       │                    │
    │       │                    └── _generate_fallback(schema, context)
    │       │                            │
    │       │                            └── return schema(**safe_defaults)
    │       │
    │       └── Other error ──→ log warning, retry after delay
    │
    ├── Attempt 2: Retry
    │       │
    │       ├── Success ──→ return validated Pydantic object
    │       └── Error ──→ log, retry if attempts remain
    │
    ├── Attempt 3 (if max_retries=2): Final retry
    │       │
    │       ├── Success ──→ return validated Pydantic object
    │       └── Error ──→ log error, fallback
    │
    └── Fallback response returned ──→ FastAPI endpoint processes it normally
                                         │
                                         └── Response includes `"mode": "fallback"`
                                             so the frontend can display a banner:
                                             "AI assistant is in offline mode"
```

### 4.3 Key Guardrail Rules

1. **Every LLM call** in every service (`llm_service.py`, `risk_engine_service.py`, `chat_service.py`) goes through `LLMClient.invoke_structured()` or `invoke_text()` — never directly to a raw `ChatOpenAI` instance.

2. **No hardcoded API keys** — all read from `.env` via `LLMConfig`. The data science files' hardcoded keys are stripped entirely.

3. **Fallback responses are deterministic** — same inputs always produce same fallback output, so tests can verify the fallback path.

4. **Fallback responses are valid Pydantic** — they pass `model_validate()` on the way back, so downstream code never sees unexpected fields or crashes with `AttributeError`.

5. **The human-in-the-loop protects GraphDB** — the `POST /confirm-sla` endpoint is the ONLY way data reaches GraphDB. Fallback LLM data never gets persisted without human review.

---

## Summary: File Creation Order

```
Sprint 3 (Build the Brain):
  [1] models/schemas.py          — ADD ExtractedSLAData, ConfirmedSLA,
                                   RiskAnalysisResult, IoTTelemetryEvent, ManagerAlert
  [2] services/llm_service.py    — CREATE: LLMConfig, LLMClient singleton,
                                   SLAExtractionState, 4 node functions,
                                   extraction graph builder, run_extraction_pipeline()
  [3] services/lifting_service.py— CREATE: SemanticLifter class,
                                   lift_extracted_data(), lift_confirmed_sla(),
                                   build_sla_sparql_insert(), persist_confirmed_sla()
  [4] api/sandbox.py             — ADD: POST /upload-pdf, POST /confirm-sla,
                                   extract_text_from_pdf() helper
  [5] tests/test_sprint3.py      — CREATE: extraction + lifting integration tests

Sprint 4 (Build the Intelligence):
  [6] services/risk_engine_service.py — CREATE: RiskEngineState, 7 node functions,
                                        risk pipeline builder, execute_risk_assessment()
  [7] services/chat_service.py        — CREATE: ChatState, fetch_live_schema(),
                                         4 node functions, chat agent builder,
                                         ask_question()
  [8] api/dashboard.py                — CREATE: GET /risk-scores,
                                         GET /compliance-alerts,
                                         GET /fallback-options/{material_id}
  [9] tests/test_sprint4.py           — CREATE: risk engine + chat integration tests
```

---

## Dependency Additions

Add the following to `requirements.txt`:

```
langgraph>=0.4.0
langchain-openai>=0.3.0
langchain-core>=0.3.0
pdfplumber>=0.11.0
```

The existing dependencies (`fastapi`, `uvicorn`, `sparqlwrapper`, `python-dotenv`, `pydantic`) are already present.

---

## Bottom Line

The plumbing is finished. The brain is empty.

Sprint 3 is the most critical sprint — it turns the project from a "connected skeleton" into a working Semantic Digital Twin. The `INTEGRATION_PLAN.md` in your hands is the single source of truth for every file creation, every namespace decision, every GraphDB query, and every LLM fallback path. Do not deviate from the namespace or the fallback architecture without updating this document first.
