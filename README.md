# Semantic Digital Twin — Supply Chain Risk Management Platform

### Cavengers Graduation Project | Backend Developer: Yousef

> **Awarded Project:** *Semantic Digital Twin for Raw Material Supply Detection and Resolution*
> **Stack:** Python 3.12 · FastAPI · LangGraph · LangChain · GraphDB (SPARQL/OWL 2) · Scikit-Learn · Pydantic v2 · pdfplumber · SPARQLWrapper
> **Architecture:** Strict 3-Tier Layered (API → Services → Knowledge Base)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Source Modules](#3-source-modules)
4. [Core Features (LangGraph & ML Pipelines)](#4-core-features-langgraph--ml-pipelines)
5. [API Endpoints](#5-api-endpoints)
6. [Data Models](#6-data-models)
7. [Resilience & Fallback Strategy](#7-resilience--fallback-strategy)
8. [Setup & Installation](#8-setup--installation)
9. [Running the Server](#9-running-the-server)
10. [Testing](#10-testing)
11. [Project Structure](#11-project-structure)
12. [Master Status Dashboard](#12-master-status-dashboard)

---

## 1. Project Overview

The **Semantic Digital Twin** is an intelligent backend platform that monitors, analyses, and mitigates supply chain disruptions in real time. It transforms unstructured supplier contracts (PDFs) into structured, machine-readable knowledge graph triples, then continuously evaluates incoming IoT telemetry against those contracts to detect delays, SLA violations, and production risks — all through a pipeline of autonomous AI agents orchestrated by LangGraph.

The system bridges four domains:

- **Document Intelligence:** Raw PDF contracts are ingested by a LangGraph-orchestrated LLM pipeline with automatic guardrails, self-correcting validation loops (up to 3 retries), and resilient fallback mechanisms that simulate LLM responses when the API is unreachable.
- **Semantic Knowledge Graph:** Extracted data is lifted into RDF triples under a strict OWL ontology namespace (`PREFIX : <http://example.org/ontology#>`) and persisted in Ontotext GraphDB, where OWL reasoning infers implicit relationships (e.g., delayed supplier → at-risk product).
- **Multi-Agent Risk Assessment:** IoT telemetry events (delay predictions, weather disruptions) trigger a LangGraph risk engine that queries the knowledge graph for SLA context, runs LLM-based risk analysis, and produces targeted manager alerts routed to the correct role (Production, Procurement, or Logistics Manager).
- **NL-to-SPARQL Chat Interface:** Users can ask supply-chain questions in natural language; a LangGraph agent translates them to SPARQL, executes them against GraphDB with automatic error self-correction, and returns human-readable answers.

A **human-in-the-loop** gate ensures that no AI-generated data reaches the knowledge graph without explicit approval from a procurement manager.

---

## 2. System Architecture

The backend follows a strict **3-Tier Layered Architecture** that enforces separation of concerns. No module in a higher layer may bypass the layer below it.

```
+------------------------------------------------------------------+
|               Layer 1: API / Controller (api/)                     |
|                                                                     |
|  Receives HTTP requests from the React frontend                    |
|  Validates all input with Pydantic schemas (auto 422 on mismatch)  |
|  Delegates to service layer — ZERO business logic, ZERO SPARQL     |
|  9 endpoints across 2 routers (sandbox + dashboard)                 |
|  All blocking DB/LLM calls dispatched via run_in_executor           |
+-----------------------------+--------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|               Layer 2: Service / Business Logic (services/)         |
|                                                                     |
|  llm_service.py       — LLMClient singleton, SLA extraction graph  |
|  lifting_service.py   — Pydantic → SPARQL INSERT, namespace guard  |
|  risk_engine_service.py — IoT → risk analysis → manager alert      |
|  chat_service.py      — NL question → SPARQL → answer (4-node)     |
|  dashboard_service.py — SPARQL query wrappers for dashboard API    |
|                                                                     |
|  All LLM calls go through LLMClient (thread-safe singleton)        |
|  with automatic retry + deterministic fallback on 429/quota errors |
+-----------------------------+--------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|               Layer 3: Knowledge Base (knowledge_base/)              |
|                                                                     |
|  connection.py  — Stateless SPARQLWrapper singleton, reads .env     |
|  repository.py  — SPARQL INSERT for SLA triples + OWL inference    |
|                   query for at-risk products                        |
|                                                                     |
|  Every SPARQL statement uses PREFIX : <http://example.org/ontology#>|
|  Named graphs: ontology axioms → http://example.org/ontology/       |
|                contract data   → http://example.org/contracts/      |
+------------------------------------------------------------------+
```

### Core Stack

| Component | Technology | Role |
|---|---|---|
| **API Framework** | FastAPI + Uvicorn 0.41 | Async HTTP server, automatic OpenAPI/Swagger docs at `/docs` |
| **Multi-Agent Orchestration** | LangGraph 1.1 | Stateful graph-based agent pipelines with conditional routing |
| **LLM Integration** | LangChain (ChatOpenAI) | Structured output extraction, free-text generation, risk analysis |
| **Knowledge Graph** | Ontotext GraphDB (SPARQL 1.1, OWL 2) | Semantic triple store with OWL reasoning engine |
| **Document Parsing** | pdfplumber 0.11 / docx / txt | Extract raw text from uploaded PDF, DOCX, and TXT contracts |
| **Data Validation** | Pydantic v2.12 | Strict schema enforcement with auto-422 rejection |
| **Predictive ML Classifiers** | Scikit-Learn (Random Forest) | Pre-trained models predicting purchase order planning delay risk and real-time logistics delays |
| **Data Processing** | Pandas & NumPy | High-performance data manipulation, feature engineering, and evaluation score decay math |
| **Resilience Layer** | Custom LLMClient singleton | Thread-safe, automatic retry (2x), deterministic fallback on 429/quota |
| **SPARQL Client** | SPARQLWrapper 2.0 | Stateless HTTP client (one fresh connection per request) |

---

## 3. Source Modules

### `main.py` — Application Entry Point
- Calls `load_dotenv()` before any other import to ensure environment variables are loaded robustly.
- Bootstraps the FastAPI app with title, description, and version `0.2.0`.
- Registers both routers: `sandbox_router` and `dashboard_router`.
- Provides a root health-check endpoint at `GET /`.

### `api/sandbox.py` — SLA Sandbox Router
- **Layer 1** controller with 5 endpoints under prefix `/api/sandbox`.
- Contains zero business logic — all intelligence lives in the service layer.
- Uses `asyncio.get_running_loop().run_in_executor()` for all blocking SPARQL/LLM calls to prevent event loop blocking.
- Imports only from `services/` and `models/` — never from `knowledge_base/` directly.

### `api/dashboard.py` — Dashboard Router
- **Layer 1** controller with 4 endpoints under prefix `/api/dashboard`.
- Zero direct `knowledge_base` imports — delegates entirely to `services/dashboard_service.py`.
- Chat endpoint calls `run_chat_pipeline_async()` which is already async-safe.

### `services/llm_service.py` — LLM Infrastructure & SLA Extraction
**Two layers of functionality:**

**1. LLM Infrastructure (`LLMConfig` + `LLMClient` singleton):**
- Thread-safe singleton with double-checked locking.
- Configurable via environment variables (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_FALLBACK_ENABLED`, `OPENAI_API_KEY`).
- `invoke_structured()` — calls LLM with `.with_structured_output(schema)` for guaranteed Pydantic output.
- `invoke_text()` — calls LLM for free-text generation.
- Both methods implement the resilience contract: try → retry (2x) → fallback (deterministic simulation).
- Handles 429, quota, rate-limit, and resource-exhausted errors gracefully.
- Falls back to `OPENAI_API_KEY` if `LLM_API_KEY` is not set.

**2. SLA Extraction Pipeline:**
- 3-node LangGraph: `[guardrail] → [extractor] → [validator]` with conditional retry loop.
- Guardrail classifies document as VALID/INVALID SLA contract.
- Extractor uses `with_structured_output(ExtractedSLAData)` to extract 9 fields.
- Validator enforces 5 semantic business rules with self-correcting feedback.
- Up to 3 retry iterations on validation failure.

### `services/lifting_service.py` — Semantic Lifting
- **Namespace Enforcement Boundary:** Every SPARQL statement MUST use `PREFIX : <http://example.org/ontology#>`. The data science team's temporary namespace is strictly forbidden.
- `SemanticLifter` class — converts validated Pydantic models into SPARQL INSERT DATA statements.
- `lift_extracted_data()` — builds a complete INSERT DATA query from `ExtractedSLAData` (supplier, material, contract, SLA properties).
- `persist_confirmed_sla()` — HITL flow: maps `ConfirmedSLA` → `SLAContract` → delegates to `create_contract_graph()`.
- `save_sla_contract()` — thin service wrapper for direct (non-HITL) persistence.
- `execute_sparql_insert()` — executes a raw SPARQL INSERT string against GraphDB.
- **Integer Day Rule:** `hours // 24` with a minimum floor of 1 day.
- SPARQL injection safety via `_escape_sparql_literal()`.

### `services/risk_engine_service.py` — Multi-Agent Risk Engine
- 3-node LangGraph: `[fetch_sla] → [analyze_risk] → [generate_alert]`.
- Node 1: Queries GraphDB for SLA context (lead time, penalty rate). Falls back to mock data when GraphDB is unreachable.
- Node 2: Risk Analyst Agent — calls LLM with `with_structured_output(RiskAnalysisResult)` combining IoT telemetry + SLA context.
- Node 3: Alert Generator — routes the risk assessment to the correct manager role via `_determine_alert_title()`:
  - `SLAViolation` → Procurement Manager
  - `ProductionDisruption` → Logistics Manager
  - `DelayEvent` → Production Manager
- All nodes protected by resilient fallback — pipeline never crashes even without an LLM API key.

### `services/chat_service.py` — NL-to-SPARQL Chat Agent
- 4-node LangGraph: `[guardrail] → [developer] → [database] → [customer_service]`.
- Node 0: Domain Guardrail — rejects off-topic questions (cooking, politics, casual chat) with a polite message.
- Node 1: SPARQL Developer — translates NL question to SPARQL SELECT using live GraphDB schema as context.
- Node 2: Database Executor — runs SPARQL against GraphDB; on syntax error, feeds error back to developer for self-correction (up to 3 retries).
- Node 3: Customer Service — translates raw JSON results to a concise human-readable answer.
- Schema cache: `fetch_live_schema()` queries GraphDB once and caches the result.

### `services/dashboard_service.py` — Dashboard Data Access
- **Layer 2** service that wraps `knowledge_base` repository functions for the dashboard API.
- `get_risk_scores()` — calls `find_impacted_products_by_supplier_delay()` and formats results with RED/GREEN traffic-light status.
- `get_compliance_alerts()` — builds a SPARQL SELECT query for all suppliers and their SLA terms.
- `get_fallback_options(material_id)` — builds a ranked SPARQL query for alternative suppliers.
- `get_impacted_products()` — returns raw inferred products (used by sandbox endpoint).

### `services/order_risk_service.py` — Purchase Order Delay Risk Assessment
- **Layer 2** service that evaluates delay risks of proposed purchase orders before placement using static ML model assets.
- Lazy-loads and caches ML artifacts (`delay_prediction_model.pkl`, `scaler.pkl`, and `model_features.json`).
- Queries Ontotext GraphDB to fetch target supplier profile details (reliability tier, historic performance, ESG score) and material metrics.
- Performs full 109-feature engineering on raw inputs, scaling features, and predicting on-time probability and risk status.

### `services/supplier_evaluator_service.py` — Batch Supplier Reliability Evaluator
- **Layer 2** service that updates supplier reliability scores dynamically based on historical transaction datasets (Excel/CSV sheets).
- Maps suppliers to GraphDB nodes and updates their reliability metrics via custom SPARQL commands.
- Calculates overall performance scores using a recency decay delay calculation, price variance calculations, and multi-criteria weighted aggregates.
- Integrates both direct file uploads and automated CSV logging when placing new purchase orders.

### `services/telemetry_simulator_service.py` — Background Telemetry Ingestion Loop
- **Layer 2** background thread that automatically replays logistics telemetry stream records.
- Reads GPS locations, route speeds, weather labels, cargo temperatures, and status codes from logistics data logs.
- Employs a pre-trained logistics delay predictor model to dynamically estimate delay hours based on weather severity and speeds.
- Constructs standardized `IoTTelemetryEvent` structures and streams them directly to the risk engine pipeline to create a live-updating dashboard.

### `knowledge_base/connection.py` — GraphDB Connection Broker
- **Golden Rule #1 — Stateless Connection:** SPARQLWrapper is stateless; each request is an independent HTTP call. No socket pool to manage, no session to close.
- Reads `GRAPHDB_URL`, `GRAPHDB_REPO`, `GRAPHDB_USER`, `GRAPHDB_PASSWORD` from `.env`.
- `execute_sparql_select()` — runs SELECT/ASK queries, returns list of dicts.
- `execute_sparql_update()` — runs INSERT/DELETE updates via POST.
- Module-level singleton `graphdb` shared across the entire application.

### `knowledge_base/repository.py` — SPARQL Graph Repository
- **Golden Rule #2 — Namespace Consistency:** Every triple uses `PREFIX : <http://example.org/ontology#>`.
- **Golden Rule — Named Graph Separation:** Ontology axioms → `http://example.org/ontology/`, Contract data → `http://example.org/contracts/`.
- `PREFIXES` — shared namespace block prepended to every SPARQL query.
- `CONTRACT_GRAPH` — named graph URI for all contract triples.
- `_sanitize_uri_fragment()` — converts human-readable names to safe URI fragments.
- `create_contract_graph()` — builds and executes a SPARQL INSERT DATA for an SLA contract.
- `find_impacted_products_by_supplier_delay()` — SPARQL SELECT that demonstrates OWL Inference (`:isAtRisk` inferred by reasoner).

### `models/schemas.py` — Pydantic Data Models
Six strict Pydantic v2 models with field constraints, examples, and OpenAPI descriptions:

| Model | Fields | Purpose |
|---|---|---|
| `SLAContract` | 4 fields | Core domain model for SLA contracts |
| `ExtractedSLAData` | 9 fields | Raw LLM extraction output before human review |
| `ConfirmedSLA` | 6 fields | Human-reviewed and corrected SLA (HITL gate) |
| `RiskAnalysisResult` | 5 fields | Structured LLM risk assessment output |
| `IoTTelemetryEvent` | 5 fields | Incoming IoT event that triggers the risk engine |
| `ManagerAlert` | 3 fields | Final alert targeted at a specific manager role |

---

## 4. Core Features (LangGraph & ML Pipelines)

### 4.1 PDF SLA Extraction with Guardrails (`services/llm_service.py`)

```
Upload PDF → [guardrail] ──INVALID──→ END (400 response)
                │
                └──VALID──→ [extractor] → [validator]
                                    ↑            │
                                    └──(error, retry<3)──┘
                                              │
                                         (success / max retries)
                                              │
                                              ↓
                                          Return ExtractedSLAData
```

- Guardrail classifies document as valid SLA or rejects with 400 error.
- Extractor calls LLM with `with_structured_output(ExtractedSLAData)` to extract 9 fields.
- Validator enforces 5 semantic rules: positive lead time (< 1 year), decimal thresholds (0.0–1.0), non-negative penalties, non-empty identifiers.
- If validation fails, the error message is injected into the re-prompt and the pipeline retries (up to 3 iterations).
- If LLM is unreachable, deterministic simulation response is returned.

### 4.2 Human-in-the-Loop Validation & Knowledge Graph Ingestion (`services/lifting_service.py`)

```
PDF Upload → LLM Extraction → Human Review → Confirm SLA → GraphDB
  [Frontend/API]    [Backend]      [Frontend]     [API]      [SPARQL]
```

- Extracted data is presented to a procurement manager for review.
- Manager can edit any field and submit the corrected payload.
- `persist_confirmed_sla()` maps `ConfirmedSLA` → `SLAContract` → calls `create_contract_graph()`.
- All triples use the strict ontology namespace `PREFIX : <http://example.org/ontology#>`.
- The data science team's temporary namespace is **strictly forbidden** at this boundary.

### 4.3 Event-Driven Risk Engine (`services/risk_engine_service.py`)

```
IoT Telemetry → [fetch_sla] → [analyze_risk] → [generate_alert] → ManagerAlert
```

- **Node 1 — SLA Context Fetcher:** Queries GraphDB for `lead_time_days` and `delay_penalty_rate` for the delivery's supplier. Falls back to deterministic mock data when GraphDB is unreachable, enabling full end-to-end testing without a running database.
- **Node 2 — Risk Analyst Agent:** Combines IoT telemetry (delay hours, reason code, disruption probability) with SLA context (lead time, penalty rate). Calls LLM with `with_structured_output(RiskAnalysisResult)`. Falls back to conservative defaults on API failure.
- **Node 3 — Alert Generator:** Routes the risk assessment to the correct manager role using the `_determine_alert_title()` logic based on risk types detected.

### 4.4 NL-to-SPARQL Chat Agent (`services/chat_service.py`)

```
Question → [guardrail] ──off-topic──→ [customer_service] → "I can only answer..."
               │
               └──valid──→ [developer] → [database] → [customer_service] → Answer
                                 ↑            │
                                 └──(error, retry<3)──┘
```

- **Node 0 — Domain Guardrail:** Classifies the question as supply-chain related or off-topic. Off-topic questions receive a polite out-of-domain message.
- **Node 1 — SPARQL Developer:** Translates NL into SPARQL SELECT using the live GraphDB schema as context. Follows 8 strict rules (multi-hop reasoning, URI handling, optional blocks, minimal queries).
- **Node 2 — Database Executor:** Runs the generated SPARQL against GraphDB. On syntax error, feeds the error back to the developer node for up to 3 self-correction attempts.
- **Node 3 — Customer Service:** Translates raw JSON results into a concise, complete human-readable answer. Lists every entity without summarization.

### 4.5 Purchase Order Delay Risk Assessment (ML Classification)

Proposed purchase orders are evaluated through a Scikit-Learn Random Forest Classifier that predicts delay risks during planning.
1. The API receives order details (`supplier_id`, `material_id`, `quantity`, `unit_price`, `po_type`, etc.).
2. The service queries Ontotext GraphDB to fetch target supplier characteristics (historical performance, reliability tier, ESG score) and contractual parameters (lead times, payment terms).
3. The system maps the inputs to a 109-feature engineering dataset, scaling features with a pre-trained `scaler.pkl`.
4. It predicts the on-time probability and flags high-risk orders, estimating the delay duration in hours to support procurement planning.

### 4.6 Real-Time Telemetry Replay & ML Logistics Regressor

To simulate active operations, the background replay simulator processes GPS coordinates, speeds, weather states, and temperatures from a logistics dataset.
1. Each telemetry record's speed, weather, and status are translated into predictive inputs.
2. A pre-trained logistics regression model predicts the estimated delay hours in real-time.
3. If an SLA breach is predicted, the event is immediately pushed to the risk engine pipeline to trigger manager alerts.

### 4.7 Live Digital Twin SLA Comparison

When a new SLA contract is uploaded or extracted, the frontend compares the proposed metrics side-by-side with the current contract active in GraphDB:
1. Queries the database using `GET /api/dashboard/active-sla` for the supplier-material combination.
2. Displays contractual terms side-by-side (lead times, unit costs, quantities, penalty rates).
3. Evaluates changes to help procurement managers easily validate modifications before pushing them to the knowledge graph.

### 4.8 Role-Based Access Control (RBAC) Alert Routing

The dashboard dynamically adjusts alerts and KPIs depending on the logged-in manager's role:
- **Procurement Manager**: Monitors supplier compliance, SLA terms, and financial penalties (such as under-shipment issues).
- **Logistics Manager**: Tracks raw material delays, shipping status, and transportation disruptions.
- **Production Manager**: Manages assembly line statuses, safety stock levels, and production process disruptions.
- **Admin**: Views aggregated, unfiltered metrics across all components.

---

## 5. API Endpoints

All endpoints return JSON. Invalid payloads receive automatic `422` responses from Pydantic validation.

### Sandbox (`/api/sandbox`)

| Method | Path | Description | Request Body | Response |
|---|---|---|---|---|
| `POST` | `/api/sandbox/upload-sla` | Directly persist an SLA contract as RDF triples in GraphDB | `SLAContract` JSON | `{"status", "message", "graph_data"}` |
| `GET` | `/api/sandbox/match-assembly-line` | Check if a material already has a linked assembly line in GraphDB | — | `{"matched", "process"}` |
| `POST` | `/api/sandbox/upload-transactions` | Parse Excel/CSV procurement sheet and batch-update reliability scores | `multipart/form-data` file | `{"status", "message", "details"}` |
| `GET` | `/api/sandbox/impacted-products` | Query OWL-inferred at-risk products from the knowledge graph | — | `{"status", "count", "impacted_products"}` |
| `POST` | `/api/sandbox/upload-pdf` | Upload a PDF contract → LLM extraction → return structured JSON for human review | `multipart/form-data` file | `{"status", "extraction_id", "extracted_data", "mapped_sla", "raw_text"}` |
| `POST` | `/api/sandbox/confirm-sla` | Human-in-the-loop confirmation → persist triples to GraphDB | `ConfirmedSLA` JSON | `{"status", "extraction_id", "supplier", "material", "graph", "triples_inserted"}` |
| `POST` | `/api/sandbox/simulate-iot` | Inject an IoT telemetry event → risk engine → return a ManagerAlert | `IoTTelemetryEvent` JSON | `ManagerAlert` JSON |
| `POST` | `/api/sandbox/predict-order-risk` | Predict PO delay risk before placement using pre-trained ML classifier | `OrderRiskPredictionRequest` | `OrderRiskPredictionResponse` |
| `POST` | `/api/sandbox/place-order` | Place PO, log to historical database, and update supplier scores | `OrderRiskPredictionRequest` | `{"status", "message", "delivery_id"}` |
| `POST` | `/api/sandbox/migrate-supplier-scores` | Set default reliability scores (0.75) for suppliers lacking them | — | `{"status", "message", "updated_count"}` |

### Dashboard (`/api/dashboard`)

| Method | Path | Description | Request Body | Response |
|---|---|---|---|---|
| `GET` | `/api/dashboard/risk-scores` | OWL-inferred at-risk products with RED/GREEN traffic-light status | — | `{"status", "count", "risk_scores"}` |
| `GET` | `/api/dashboard/compliance-alerts` | All suppliers and their SLA terms from GraphDB | — | `{"status", "count", "alerts"}` |
| `GET` | `/api/dashboard/fallback-options/{material_id}` | Alternative suppliers for a material, ranked by reliability score | — | `{"status", "count", "material", "suppliers"}` |
| `GET` | `/api/dashboard/active-sla` | Fetch existing active SLA details for comparison on PDF upload | — | `{"status", "exists", "sla"}` |
| `POST` | `/api/dashboard/assign-fallback` | Assign alternative supplier to replace at-risk primary supplier | `FallbackAssignmentRequest` | `{"status", "message"}` |
| `GET` | `/api/dashboard/kpis` | Retrieve high-level KPIs, optionally filtered by user role | — | `{"status", "kpis"}` |
| `GET` | `/api/dashboard/alerts` | List all active ML-generated system alerts | — | `{"status", "count", "alerts"}` |
| `GET` | `/api/dashboard/assembly-lines` | List all active production process names from the knowledge graph | — | `{"status", "assembly_lines"}` |
| `POST` | `/api/dashboard/assign-material-process` | Assign a material to an assembly line and dismiss alert | `AssignMaterialRequest` | `{"status", "message"}` |
| `POST` | `/api/dashboard/request-fallback` | Generate an urgent fallback request alert for a material | `FallbackRequest` | `{"status", "alert_id", "severity", "risk_percent"}` |
| `POST` | `/api/dashboard/alerts/mark-read` | Mark a specific system alert's status as READ | `AlertStatusUpdate` | `{"status", "message"}` |
| `POST` | `/api/dashboard/alerts/dismiss` | Mark a specific system alert's status as DISMISSED | `AlertStatusUpdate` | `{"status", "message"}` |
| `POST` | `/api/dashboard/chat` | Natural-language supply-chain question → SPARQL → human-readable answer | `{"question", "chat_history"}` | `{"status", "answer", "sparql", "results", "topic_accepted"}` |

### Example: `POST /api/sandbox/simulate-iot`

```bash
curl -X POST http://localhost:8001/api/sandbox/simulate-iot \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_id": "DEL_001",
    "estimated_delay_hours": 48,
    "reason_code": "Weather_Delay",
    "disruption_probability": 0.9,
    "timestamp": "2026-03-05T15:30:00Z"
  }'
```

**Response (200):**
```json
{
  "manager_title": "Production Manager",
  "alert_text": "Delivery DEL_001 is at risk. Delay: 48h (Weather_Delay). SLA lead time: 3 day(s). Severity: High. Risks detected: DelayEvent, SLAViolation. Estimated penalty: $12,500.00. Reasoning: 48h delay exceeds 72h SLA lead time. Inventory below safety stock.",
  "validated": false
}
```

### Example: `POST /api/dashboard/chat`

```bash
curl -X POST http://localhost:8001/api/dashboard/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What materials does Supplier 001 supply?"}'
```

**Response (200):**
```json
{
  "status": "success",
  "answer": "Supplier 001 supplies Titanium and Steel Coil.",
  "sparql": "PREFIX : <http://example.org/ontology#> ...",
  "results": [...],
  "topic_accepted": true
}
```

---

## 6. Data Models

All models defined in `models/schemas.py` using Pydantic v2 with strict validation, examples, and OpenAPI descriptions.

### SLAContract

| Field | Type | Constraints | Description |
|---|---|---|---|
| `supplier_name` | `str` | min_length=1 | Name of the raw-material supplier |
| `material` | `str` | min_length=1 | Raw material covered by this SLA |
| `lead_time_days` | `int` | gt=0 | Delivery lead time in days |
| `penalty_clause` | `str` | min_length=1 | Penalty clause description |
| `quantity` | `int` | ge=0 | Standard order quantity covered under SLA |
| `unit_cost` | `float` | ge=0.0 | Unit cost of the material |
| `impacted_process` | `str \| None` | optional | Production process or assembly line impacted by this material |
| `is_fallback` | `bool` | default False | Whether this contract is for a backup/alternative supplier |
| `delay_penalty_rate` | `float \| None` | ge=0.0 | Daily delay penalty rate |
| `missed_item_penalty_rate` | `float \| None` | ge=0.0 | Penalty rate per missed/short-shipped item |
| `min_quality_threshold` | `float \| None` | 0.0–1.0 | Minimum acceptable quality threshold (decimal) |
| `quality_penalty_rate` | `float \| None` | 0.0–1.0 | Quality penalty rate as a decimal |

### ExtractedSLAData

| Field | Type | Constraints | Description |
|---|---|---|---|
| `document_id` | `str` | auto-generated UUID | Unique extraction trace ID |
| `supplier_id` | `str` | min_length=1 | Supplier/vendor identifier |
| `supplier_name` | `str` | min_length=1 | Human-readable supplier name |
| `material` | `str` | min_length=1 | Raw material name |
| `sla_lead_time_hours` | `int` | gt=0 | Lead time in hours |
| `delay_penalty_rate` | `float` | ge=0.0 | Penalty for delayed delivery |
| `missed_item_penalty_rate` | `float` | ge=0.0 | Penalty for short-shipments |
| `minimum_quality_threshold` | `float` | 0.0–1.0 | Minimum yield (decimal) |
| `quality_penalty_rate` | `float` | 0.0–1.0 | Sub-quality penalty (decimal) |
| `quantity` | `int` | ge=0, default 0 | Standard order quantity or quantity covered under SLA |
| `unit_cost` | `float` | ge=0.0, default 0.0 | Unit cost of the material |

### ConfirmedSLA

| Field | Type | Constraints | Description |
|---|---|---|---|
| `extraction_id` | `str` | required | Links back to the LLM extraction trace |
| `supplier_name` | `str` | min_length=1 | Human-verified supplier name |
| `material` | `str` | min_length=1 | Human-verified material name |
| `lead_time_days` | `int` | gt=0 | Delivery lead time in days |
| `penalty_clause` | `str` | min_length=1 | Human-edited penalty description |
| `corrections` | `str \| None` | optional | Reviewer notes about corrections |
| `quantity` | `int` | ge=0 | Standard order quantity or quantity covered under SLA |
| `unit_cost` | `float` | ge=0.0 | Unit cost of the material |
| `impacted_process` | `str \| None` | optional | Production process or assembly line impacted by this material |
| `is_fallback` | `bool` | default False | Whether this contract is for a backup/alternative supplier |
| `delay_penalty_rate` | `float \| None` | ge=0.0 | Daily delay penalty rate |
| `missed_item_penalty_rate` | `float \| None` | ge=0.0 | Penalty rate per missed/short-shipped item |
| `min_quality_threshold` | `float \| None` | 0.0–1.0 | Minimum acceptable quality threshold (decimal) |
| `quality_penalty_rate` | `float \| None` | 0.0–1.0 | Quality penalty rate as a decimal |

### RiskAnalysisResult

| Field | Type | Constraints | Description |
|---|---|---|---|
| `risks` | `list[str]` | required | Active risk types (e.g., DelayEvent, SLAViolation) |
| `confidence` | `float` | 0.0–1.0 | Confidence score of the analysis |
| `severity` | `str` | required | Low, Medium, High, or Critical |
| `financial_penalty_estimate` | `float` | ge=0.0 | Estimated penalty amount in USD |
| `reasoning` | `str` | required | Human-readable explanation from the LLM |

### IoTTelemetryEvent

| Field | Type | Constraints | Description |
|---|---|---|---|
| `delivery_id` | `str` | min_length=1 | Unique delivery/shipment identifier |
| `estimated_delay_hours` | `int` | ge=0 | ML-predicted or IoT-reported delay in hours |
| `reason_code` | `str` | required | Machine-readable delay reason code |
| `disruption_probability` | `float` | 0.0–1.0 | Probability of production disruption |
| `timestamp` | `str` | required | ISO 8601 timestamp |
| `quantity` | `int` | ge=0, default 0 | Number of units in this delivery shipment |

### ManagerAlert

| Field | Type | Constraints | Description |
|---|---|---|---|
| `manager_title` | `str` | required | Production Manager, Procurement Manager, or Logistics Manager |
| `alert_text` | `str` | min_length=1 | Alert message body from the multi-agent pipeline |
| `validated` | `bool` | default False | Whether the alert passed the validator quality gate |

### OrderRiskPredictionRequest

| Field | Type | Constraints | Description |
|---|---|---|---|
| `supplier_id` | `str` | required | Unique identifier (URI or ID) of the supplier in GraphDB |
| `material_id` | `str` | required | Unique identifier (URI or ID) of the raw material in GraphDB |
| `quantity` | `int` | ge=1 | Proposed order quantity |
| `unit_price` | `float` | ge=0.0 | Proposed unit price |
| `po_date` | `str` | required | Proposed purchase order date (YYYY-MM-DD) |
| `po_type` | `str` | default "Standard" | Type of purchase order (Standard, Emergency) |
| `department` | `str` | default "Operations" | Department requesting the order |

### OrderRiskPredictionResponse

| Field | Type | Constraints | Description |
|---|---|---|---|
| `status` | `str` | default "success" | Evaluation status |
| `on_time_probability` | `float` | 0.0–1.0 | Model-predicted probability that the order will arrive on time |
| `risk_level` | `str` | required | Calculated risk classification level based on probability threshold |
| `estimated_delay_hours` | `int` | ge=0 | Estimated delay duration in hours if flagged as high-risk |
| `features_used` | `dict` | required | Explainability dictionary showing parameters retrieved from GraphDB |

---

## 7. Resilience & Fallback Strategy

The system is designed to work **without any external API keys** in fallback simulation mode.

### LLM Fallback Chain

```
LLM Call → Try primary model
            ├── Success → Return result
            ├── 429/Quota/Exhausted → Return deterministic fallback (simulated data)
            └── Other error → Retry (2x with 1s delay)
                              ├── Success → Return result
                              └── All retries failed → Return fallback (if enabled) or raise
```

- `LLM_FALLBACK_ENABLED=true` in `.env` enables deterministic simulation mode with hand-crafted mock responses.
- `ExtractedSLAData` fallback: safe defaults (72h lead time, $500 delay penalty, 98% quality threshold).
- `RiskAnalysisResult` fallback: conservative "Low" severity with "DelayEvent" risk.
- Text fallback: `"[Fallback Response] The AI assistant is currently in offline mode..."`.
- This allows every endpoint to be tested end-to-end without a live API key.

### GraphDB Fallback Chain

- `risk_engine_service.py` tries real GraphDB queries first; on failure, uses hard-coded mock SLA data.
- `dashboard_service.py` and `chat_service.py` require GraphDB for full data, but the LLM fallback within pipelines keeps the system responsive.
- The entire 3-tier architecture never throws unhandled exceptions — every layer has a safety net.

---

## 8. Setup & Installation

### Prerequisites

- Python 3.12+
- Ontotext GraphDB (optional — the system runs in fallback simulation mode without it)

### 1. Clone & Navigate

```bash
cd "AI-Supply-Chain-Risk-Engine"
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
cd Backend
pip install -r requirements.txt
```

Or install the core packages manually:

```bash
pip install fastapi uvicorn sparqlwrapper python-dotenv pydantic pdfplumber \
            langgraph langchain-core langchain-openai python-multipart
```

### 4. Configure Environment

Create (or edit) `Backend/.env`:

```env
# GraphDB Configuration
GRAPHDB_URL=http://localhost:7200
GRAPHDB_REPO=SLA_DigitalTwin

# Optional: GraphDB authentication
GRAPHDB_USER=
GRAPHDB_PASSWORD=

# LLM Configuration (optional — fallback mode works without it)
OPENAI_API_KEY=mock-key-for-sandbox-presentation
LLM_FALLBACK_ENABLED=true

# Alternative: OpenRouter configuration
# LLM_API_KEY=sk-or-v1-your-key-here
# LLM_BASE_URL=https://openrouter.ai/api/v1
```

> **`LLM_FALLBACK_ENABLED=true`** enables deterministic simulation mode when no API key is configured or when the LLM provider returns a 429 quota error. This lets you test every endpoint end-to-end without a live API key.

> **`OPENAI_API_KEY`** is used as a fallback when `LLM_API_KEY` is not set. The `LLMClient._ensure_llm()` method checks `LLM_API_KEY` first, then falls back to `OPENAI_API_KEY`.

---

## 9. Running the Server

### Start Uvicorn

```bash
cd Backend
python -m uvicorn main:app --reload --port 8001
```

> Port `8001` avoids the Windows `[WinError 10013]` socket permission error on port 8000.

### Open Swagger UI

Navigate to [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) to explore and test all nine endpoints interactively with automatic OpenAPI documentation.

### Smoke Test (Health Check)

```bash
curl http://localhost:8001/
# {"message":"Hello Cavengers! The Backend is alive! (GraphDB Edition)"}
```

### Test the Risk Engine (Fallback Mode — no API key required)

```bash
curl -X POST http://localhost:8001/api/sandbox/simulate-iot \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_id": "DEL_001",
    "estimated_delay_hours": 48,
    "reason_code": "Weather_Delay",
    "disruption_probability": 0.9,
    "timestamp": "2026-03-05T15:30:00Z"
  }'
```

### Test the Chat (Fallback Mode)

```bash
curl -X POST http://localhost:8001/api/dashboard/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What materials does Supplier 001 supply?"}'
```

### Test PDF Upload (Fallback Mode)

```bash
# Create a minimal fake SLA PDF and upload it
# The guardrail will accept it in fallback mode and return simulated extraction data
```

---

## 10. Testing

The backend includes a comprehensive suite of unit and integration tests located in the `tests/` directory to validate all components, ML predictions, and GraphDB semantic behaviors.

### Integration Test Suite (70 assertions, no external dependencies)

```bash
cd Backend
python -m tests.test_integration
```

This suite validates:
1. All 8 Pydantic model instantiations (including ML requests and responses)
2. LLMClient singleton thread-safety
3. Deterministic fallback generation for ExtractedSLAData, RiskAnalysisResult, and free-text
4. Extraction pipeline topology (3 nodes + conditional edges)
5. Risk engine pipeline topology (3 nodes + linear edges)
6. Chat pipeline topology (4 nodes + conditional edges)
7. Semantic lifter namespace enforcement (ontology prefix, banned namespace detection)
8. Hours-to-days conversion (Integer Day Rule with floor to 1)
9. SPARQL literal escaping (quotes, backslashes, newlines)
10. URI builder helpers (supplier, contract, material)
11. Dashboard endpoint wiring
12. Sandbox endpoint wiring
13. SPARQL injection safety (quotes in names properly escaped)
14. Initial state construction for pipelines

### GraphDB Connection Test Suite (requires running GraphDB)

```bash
cd Backend
python -m tests.test_graphdb_connection
```

This suite validates:
1. GraphDB endpoint reachability
2. Triple insertion (INSERT DATA + verification SELECT)
3. OWL inference validation (detecting `sys:inferred` triples)

### Predictive ML Integration Test Suite

```bash
cd Backend
python -m tests.test_order_risk
```

This suite validates:
1. ML asset lazy-loading and validation of pre-trained random forest classification models
2. Feature engineering scaling and feature set integrity (109 columns)
3. Risk level categorizations and delay duration estimation math

### Recalculation & Score Ingestion Test Suite

```bash
cd Backend
python -m tests.test_supplierScore_updates
```

This suite validates:
1. Exponential delay penalty scoring and transaction recency decay math
2. Integration of transaction Excel sheets to recalculate reliability scores in GraphDB

### Supplier Fallback E2E Test Suite

```bash
cd Backend
python -m tests.test_fallback_e2e
```

This suite validates:
1. Primary supplier risk detection and fallback supplier routing
2. Verification of alternate supplier assignment endpoints in the knowledge graph

---

## 11. Project Structure

```
AI-Supply-Chain-Risk-Engine/
│
├── README.md                        # This file — comprehensive project documentation
├── Historical_Transactions.xlsx     # Historical transaction log sheet
│
├── Backend/                         # Main backend application
│   │
│   ├── api/                         # Layer 1: API Controllers
│   │   ├── __init__.py
│   │   ├── sandbox.py               # SLA upload, PDF, HITL confirm, IoT, impacted products, PO prediction/placement
│   │   └── dashboard.py             # Risk scores, compliance, fallback, active-sla, RBAC KPIs, alerts, assembly lines
│   │
│   ├── services/                    # Layer 2: Business Logic
│   │   ├── __init__.py
│   │   ├── llm_service.py           # LLMConfig, LLMClient singleton, SLA extraction LangGraph
│   │   ├── lifting_service.py       # Semantic lifting (Pydantic → SPARQL INSERT), namespace guard
│   │   ├── risk_engine_service.py   # Multi-agent risk engine LangGraph (IoT → alert)
│   │   ├── chat_service.py          # NL-to-SPARQL chat agent LangGraph
│   │   ├── dashboard_service.py     # Dashboard SPARQL query wrappers & KPI calculations
│   │   ├── order_risk_service.py    # Purchase Order delay risk ML classification & feature engineering
│   │   ├── supplier_evaluator_service.py # Batch supplier score calculation & Ontotext GraphDB persistence
│   │   └── telemetry_simulator_service.py # Replays telemetry logs, runs logistics ML delay regressor
│   │
│   ├── knowledge_base/              # Layer 3: Data Access
│   │   ├── __init__.py
│   │   ├── connection.py            # Stateless GraphDB SPARQLWrapper singleton
│   │   └── repository.py            # SPARQL INSERT/SELECT helpers, OWL inference query
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py               # 8 Pydantic v2 models (SLAContract, OrderRiskPredictionRequest, etc.)
│   │   └── ml_assets/               # Pre-trained ML classifiers & scalers
│   │       ├── delay_prediction_model.pkl
│   │       ├── scaler.pkl
│   │       ├── model_features.json
│   │       ├── logistics_delay_model.pkl
│   │       └── logistics_model_features.json
│   │
│   ├── scripts/                     # Operational, testing, and training utilities
│   │   ├── train_logistics_model.py # Logistics ML model training script
│   │   ├── generate_telemetry_stream.py # Generator for telemetry stream logs
│   │   ├── check_query.py           # SPARQL test verification utility
│   │   └── inject_test_delay.py     # Database event simulation injections
│   │
│   ├── tests/                       # Unit & integration test suites
│   │   ├── __init__.py
│   │   ├── test_integration.py      # Core API & service integration test suite (70 assertions)
│   │   ├── test_graphdb_connection.py # GraphDB verification suite (insert, select, OWL inference)
│   │   ├── test_order_risk.py       # PO prediction ML integration test suite
│   │   ├── test_supplierScore_updates.py # Supplier reliability recalculation tests
│   │   └── test_fallback_e2e.py     # Supplier fallback assignment validation
│   │
│   ├── docs/
│   │   └── How to run.txt              # Quick-start instructions
│   │
│   ├── main.py                      # FastAPI app bootstrap, router registration, health check
│   ├── requirements.txt             # Pinned python package requirements
│   ├── .env                         # Local environment configurations (GraphDB URIs, API keys)
│   └── .gitignore                   # Local git ignore configurations
│
└── Frontend/my-app/                 # React-based digital twin dashboard app
    ├── src/
    │   ├── auth/                    # Role-based access control setup (roles.js)
    │   ├── components/layout/       # App layout & Topbar (role selection, alert notifications dropdown)
    │   ├── pages/                   # Main view panels
    │   │   ├── Dashboard.jsx        # Role-based KPI stats, alerts log, and reliability graphs
    │   │   ├── Suppliers.jsx        # Supplier profiles, compliance overview, and performance trends
    │   │   ├── SLAUpload.jsx        # Contract PDF parsing, active SLA digital twin side-by-side comparison
    │   │   ├── InventoryRisk.jsx    # Live inventory monitoring, assembly line selection, primary/fallback suppliers
    │   │   ├── Alerts.jsx           # System alerts overview pane
    │   │   └── ChatAssistant.jsx    # NL-to-SPARQL Chat Assistant panel
    │   └── services/
    │       └── api.js               # Frontend API service layer (FastAPI interaction client)
```

---

## 12. Master Status Dashboard

### Overall Progress — 33/33 components complete

| Layer | Component | Status | Notes |
|---|---|---|---|
| **Project Structure** | Repository layout, all `__init__.py` packages | Complete | Monorepo with clean separation |
| **Project Structure** | `venv` + `requirements.txt` with pinned deps | Complete | Fully reproducible environment |
| **Project Structure** | `.env` + `.gitignore` | Complete | Secrets excluded from git, temp files cleaned up |
| **API Layer** | FastAPI app bootstrap with `load_dotenv()` | Complete | Env vars loaded at import time |
| **API Layer** | Router registration (sandbox + dashboard) | Complete | 2 routers, 22 endpoints |
| **API Layer** | Health-check endpoint `GET /` | Complete | Returns alive message |
| **API Layer** | `POST /api/sandbox/upload-sla` | Complete | Delegates to `lifting_service.save_sla_contract()` |
| **API Layer** | `GET /api/sandbox/impacted-products` | Complete | Delegates to `dashboard_service.get_impacted_products()` |
| **API Layer** | `POST /api/sandbox/upload-pdf` | Complete | PDF → LLM extraction → structured JSON |
| **API Layer** | `POST /api/sandbox/confirm-sla` | Complete | HITL gate → persists to GraphDB |
| **API Layer** | `POST /api/sandbox/simulate-iot` | Complete | IoT telemetry → risk engine → ManagerAlert |
| **API Layer** | `GET /api/dashboard/risk-scores` | Complete | OWL-inferred RED/GREEN risk status |
| **API Layer** | `GET /api/dashboard/compliance-alerts` | Complete | SLA terms from knowledge graph with grace periods |
| **API Layer** | `GET /api/dashboard/fallback-options/{id}` | Complete | Alternative suppliers ranked by reliability |
| **API Layer** | `POST /api/dashboard/chat` | Complete | NL question → SPARQL → human answer |
| **API Layer** | `GET /api/dashboard/active-sla` | Complete | Fetches active SLA details for UI comparison |
| **Services Layer** | `LLMClient` with 429/quota fallback | Complete | Thread-safe singleton, 2x retry, deterministic fallback |
| **Services Layer** | `LLMConfig` with env-var configuration | Complete | Provider-agnostic (OpenRouter, OpenAI, etc.) |
| **Services Layer** | SLA Extraction LangGraph (3 nodes + retry) | Complete | Guardrail → Extractor → Validator (self-correcting) |
| **Services Layer** | Semantic Lifting (JSON → RDF) | Complete | Pydantic to SPARQL INSERT, namespace enforcement |
| **Services Layer** | Risk Engine LangGraph (3 nodes) | Complete | IoT → SLA fetch → analysis → alert routing |
| **Services Layer** | NL-to-SPARQL Chat Agent (4 nodes) | Complete | Guardrail → Developer → Database → Customer Service |
| **Services Layer** | Dashboard Service (SPARQL query wrappers) | Complete | Isolates SPARQL from API layer |
| **Services Layer** | Predictive ML (`order_risk_service.py`) | Complete | Random Forest classifier for PO delay risk |
| **Services Layer** | Telemetry Replay (`telemetry_simulator.py`) | Complete | Background thread streaming IoT logs + ML delay predictions |
| **Data Models** | 8 Pydantic v2 schemas | Complete | SLAContract, ConfirmedSLA, IoTTelemetryEvent, OrderRisk request/response, etc. |
| **Knowledge Base** | GraphDB connection (SPARQLWrapper singleton) | Complete | Stateless, env-configured, no session management |
| **Knowledge Base** | Repository (INSERT + OWL inference query) | Complete | `create_contract_graph()`, `find_impacted_products_by_supplier_delay()` |
| **Testing** | Unit & Integration suites (test files) | Complete | test_integration, test_graphdb, test_order_risk, test_fallback_e2e, etc. |
| **Documentation** | README, How to run.txt | Complete | Standard documentation files (redundant plans cleaned up) |
| **Frontend UI** | React dashboard with role selection (RBAC) | Complete | Role-specific views (Procurement, Production, Logistics, Admin) |
| **Frontend UI** | Digital Twin SLA Side-by-Side Comparison | Complete | Interactive comparison of uploaded SLA contract against active database |
| **Frontend UI** | Live Inventory & Supplier Fallback assignment | Complete | Supports details modals, search, and fallback updates |

### Architecture Compliance

| Rule | Status | Detail |
|---|---|---|
| API must NOT import `knowledge_base` directly | ✅ Enforced | Zero `knowledge_base` imports in `api/` layer |
| API must delegate to Services | ✅ Enforced | All endpoints call `services.*` only |
| Services may import `knowledge_base` | ✅ Correct | `lifting_service`, `dashboard_service`, `chat_service`, `order_risk_service` |
| Blocking calls must use `run_in_executor` | ✅ Enforced | All blocking sandbox & ML endpoints wrapped in run_in_executor |
| `load_dotenv()` must be called at startup | ✅ Enforced | Called in `main.py` before any import |
| All SPARQL must use project namespace | ✅ Enforced | Golden Rule #2 in `repository.py` |
| Named graph separation (ontology vs data) | ✅ Enforced | Golden Rule in `repository.py` |

### Traffic Light Summary

| Status | Count | Items |
|---|---|---|
| ✅ **Complete** | 33/33 | All layers, endpoints, pipelines, ML models, tests, docs, and React frontend pages |
| 🟡 **In Progress** | 0 | — |
| 🔴 **Not Started** | 0 | — |
| 📋 **Future** | — | Streamlit sandbox frontend, MQTT physical IoT bridge integration |

---

> **Bottom Line:** The supply chain digital twin platform is fully implemented, production-ready, and architecture-compliant. All backend services, including the four LangGraph pipelines (PDF extraction, semantic lifting, risk engine, NL-to-SPARQL chat) and the Random Forest PO risk predictor, are operational with industrial-grade resilience (double-checked lock singleton, 429/quota fallback, deterministic simulation mode). The background telemetry simulator streams real logistics data and predicts delay hours dynamically, keeping the dashboard "live". The React frontend enforces role-based access control (Procurement, Production, Logistics) with dedicated views, fallback assignment, and side-by-side SLA digital twin comparison. **All 33 components are complete.**
