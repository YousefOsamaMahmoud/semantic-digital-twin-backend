<div align="center">

# Semantic Digital Twin — Supply Chain Risk Detection & Mitigation Platform

**Real-Time Supply Chain Risk Detection Engine · OWL 2 Semantic Reasoning · LangGraph Multi-Agent Orchestration · Predictive ML & Role-Based React Dashboard**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.132-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.1-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini_%2F_LLMs-NLP_Pipeline-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Ontotext GraphDB](https://img.shields.io/badge/GraphDB_%2F_Neo4j-SPARQL_1.1_%26_OWL_2-E10098?style=for-the-badge&logo=graphql&logoColor=white)](https://graphdb.ontotext.com/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.9-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![React](https://img.shields.io/badge/React-19.2-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2.12-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](./LICENSE)

</div>

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Semantic Reasoning, OWL 2 Ontology & SPARQL Inference](#3-semantic-reasoning-owl-2-ontology--sparql-inference)
4. [LangGraph Multi-Agent & NLP Extraction Pipelines](#4-langgraph-multi-agent--nlp-extraction-pipelines)
5. [Machine Learning Delay Prediction & Supplier Scoring](#5-machine-learning-delay-prediction--supplier-scoring)
6. [React Frontend & Role-Based Control Tower](#6-react-frontend--role-based-control-tower)
7. [REST API Reference](#7-rest-api-reference)
8. [Data Models & Schemas](#8-data-models--schemas)
9. [Resilience & Deterministic Fallback Strategy](#9-resilience--deterministic-fallback-strategy)
10. [Monorepo Folder Structure](#10-monorepo-folder-structure)
11. [Local Setup & Installation](#11-local-setup--installation)
12. [Testing & Verification](#12-testing--verification)

---

## 1. Executive Summary

The **Semantic Digital Twin** is an end-to-end, real-time supply chain risk detection and mitigation platform built across four tightly integrated domains: **Backend (`FastAPI` + `LangGraph`)**, **Semantic Knowledge Graph (`Ontotext GraphDB` / `OWL 2` / `RDFLib` / `Neo4j`-compatible graph workflows)**, **Machine Learning (`Scikit-Learn`)**, and an interactive **Control Tower Frontend (`React 19`)**.

It transforms unstructured supplier Service Level Agreement (SLA) contracts (PDF, DOCX, TXT) into machine-readable RDF triples, continuously evaluates live IoT logistics telemetry and purchase orders using predictive ML models, and applies OWL 2 semantic reasoning to infer cascading production risks before assembly lines halt.

### Core Capabilities

- **NLP Contract-to-RDF Pipeline (Google Gemini / OpenRouter / OpenAI LLMs + LangGraph):** Ingests raw PDF/DOCX/TXT SLA contracts through a 3-node self-correcting LangGraph workflow (`Guardrail → Extractor → Semantic Validator`) with up to 3 retry loops, Human-in-the-Loop (HITL) review, live side-by-side Digital Twin SLA diffing, and deterministic semantic lifting into RDF triples.
- **OWL 2 Ontology & Automated SPARQL Inference:** Models the entire manufacturing supply chain under `PREFIX : <http://example.org/ontology#>` (Suppliers, Raw Materials, SLA Contracts, Purchase Orders, Inventory Buffers, Assembly Lines, and Finished Products). GraphDB's OWL reasoner automatically infers `:isAtRisk` and `:hasStatus` cascades when supplier deliveries breach contractual thresholds or safety stock buffers are compromised.
- **Real-Time IoT Risk Engine & Multi-Agent Alert Routing:** Background telemetry streaming + on-demand IoT injection trigger a 3-node LangGraph Risk Engine (`Fetch SLA Context → Risk Analyst Agent → Role-Targeted Alert Generator`) that computes financial penalties and routes actionable alerts to **Procurement**, **Logistics**, or **Production** managers.
- **Dual Predictive ML Engine (Procurement + Logistics):**
  - *Procurement Model:* A 300-estimator `RandomForestClassifier` with 109 engineered features that predicts Purchase Order (PO) delay probability and risk tier *before* an order is placed.
  - *Logistics Model:* A transit delay regression pipeline that predicts real-time shipment delay hours from GPS speed, route congestion, weather severity, and cargo telemetry.
  - *Dynamic Supplier Evaluator:* Exponential recency-decay scoring engine (`supplier_evaluator_service.py`) that recalculates supplier reliability scores in GraphDB from historical transaction sheets and live PO completions.
- **NL-to-SPARQL Conversational Assistant:** A 4-node LangGraph agent (`Domain Guardrail → SPARQL Developer → GraphDB Executor → Customer Service`) that translates natural-language supply-chain questions into live SPARQL 1.1 queries with automatic syntax error self-correction.

---

## 2. System Architecture

The platform enforces a **Strict 3-Tier Layered Backend Architecture** (`API Controllers → Business & Agent Services → Knowledge Base`) coupled with dedicated **Data Science**, **Machine Learning**, and **React Frontend** workspaces.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        React 19 Control Tower (Frontend/my-app)                        │
│   RBAC Views (Procurement · Production · Logistics · Admin) · Live KPIs & Alerts       │
│   Side-by-Side Digital Twin SLA Comparison · Inventory Risk · NL-to-SPARQL Chat        │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP / REST JSON (Port 3000 → Port 8001)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     Layer 1: FastAPI Controllers (Backend/api/)                        │
│   • api/sandbox.py   (10 endpoints: SLA PDF upload, HITL confirm, IoT, PO ML risk)     │
│   • api/dashboard.py (13 endpoints: OWL risk scores, KPIs, alerts, fallback, NL chat)  │
│   • Strict Pydantic v2 validation (auto-422) · Async non-blocking run_in_executor      │
│   • Zero business logic · Zero direct knowledge_base imports                           │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               Layer 2: Multi-Agent, ML & Domain Services (Backend/services/)           │
│   • llm_service.py                 — Thread-safe LLMClient (Gemini / OpenRouter /      │
│                                      OpenAI) + 3-node SLA Extraction LangGraph         │
│   • lifting_service.py             — SemanticLifter (Pydantic → SPARQL INSERT DATA)    │
│   • risk_engine_service.py         — 3-node IoT Risk Analysis & Alert Routing Graph    │
│   • chat_service.py                — 4-node NL-to-SPARQL Self-Correcting Agent         │
│   • order_risk_service.py          — 109-feature Random Forest PO Delay Predictor      │
│   • telemetry_simulator_service.py — Background IoT Replay + Logistics ML Regressor    │
│   • supplier_evaluator_service.py  — Recency-Decay Supplier Reliability Scoring        │
│   • dashboard_service.py           — SPARQL Query Wrappers, RBAC KPIs & Fallbacks      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                 Layer 3: Semantic Knowledge Base (Backend/knowledge_base/)             │
│   • connection.py — Stateless SPARQLWrapper HTTP Broker (.env configured)              │
│   • repository.py — Named Graph Separation & OWL 2 Inference Queries                   │
│     ├─ Ontology Graph : <http://example.org/ontology/>                                 │
│     ├─ Contract Graph : <http://example.org/contracts/>                                │
│     └─ Default Namespace: PREFIX : <http://example.org/ontology#>                      │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### Technology Stack Overview

| Layer / Domain | Technology | Purpose |
|---|---|---|
| **API & Runtime** | Python 3.12+, FastAPI 0.132, Uvicorn 0.41 | High-throughput async REST API with automatic OpenAPI/Swagger documentation |
| **Agent Orchestration** | LangGraph 1.1, LangChain 1.2 | Stateful cyclic multi-agent workflows with guardrails and self-correction loops |
| **LLM & NLP Providers** | `google-genai` (Google Gemini), `langchain-google-genai`, `langchain-openai` (OpenRouter / DeepSeek / GPT) | Structured SLA contract extraction (`with_structured_output`), risk reasoning, and NL-to-SPARQL generation |
| **Semantic Graph & Reasoning** | Ontotext GraphDB, OWL 2 RL/Horst, SPARQL 1.1, RDFLib 7.6, Neo4j Driver 6.1 | RDF triple storage, named graph isolation, automated ontology inference, and graph queries |
| **Machine Learning** | Scikit-Learn 1.9, Pandas 3.0, NumPy 2.4 | Random Forest procurement delay classification, transit delay regression, supplier reliability scoring |
| **Document Parsing** | `pdfplumber`, `pdfminer.six`, `pypdfium2`, `python-docx`, `openpyxl` | Multi-format ingestion for PDF, DOCX, TXT contracts and Excel/CSV transaction logs |
| **Data Validation** | Pydantic v2.12 | Strict request/response schema validation and structured LLM output enforcement |
| **Frontend UI** | React 19.2, React Scripts 5.0, CSS Variables | Role-based Supply Chain Control Tower dashboard |

---

## 3. Semantic Reasoning, OWL 2 Ontology & SPARQL Inference

The semantic layer (`Data_Science/ontology/` and `Backend/knowledge_base/`) models supply chain entities and domain axioms using **OWL 2** (`Semantic Digital Twin Project.rdf` and `Semantic Digital Twin Project Inferred.rdf`).

### Golden Rules of the Knowledge Graph

1. **Stateless Graph Broker (`connection.py`):** Uses `SPARQLWrapper` over stateless HTTP requests (`SELECT`/`ASK` on the query endpoint, `INSERT DATA`/`DELETE` on the `/statements` endpoint) so there is zero socket pool exhaustion or driver lock contention.
2. **Strict Namespace Enforcement (`lifting_service.py` & `repository.py`):** Every triple persisted into production enforces `PREFIX : <http://example.org/ontology#>`. Any legacy or temporary namespace (`http://www.semanticweb.org/supplychain#`) is blocked at the lifting boundary.
3. **Named Graph Isolation:**
   - **Ontology Axioms:** `<http://example.org/ontology/>`
   - **Contract & Operational Triples:** `<http://example.org/contracts/>`

### Automated Risk Propagation via OWL Reasoning

When an IoT delivery delay or under-shipment event is recorded, or when a supplier's reliability score degrades, GraphDB evaluates the ontology rules and operational status across connected entities:

```
(:Supplier) ──:supplies──► (:Material) ──:usedInProcess──► (:ProductionProcess / AssemblyLine)
     │                          │                                       │
:hasSLAContract          :hasSafetyStock /                        :producesProduct
     ▼                   :currentInventory                              ▼
(:SLAContract)                  │                                  (:Product)
  • :hasLeadTimeDays            └──► Status Cascade:                    │
  • :hasDelayPenaltyRate             🟢 GREEN (Healthy Buffer)          ├──► :isAtRisk true
  • :hasMinQualityThreshold          🟡 YELLOW (Buffer Depleting)       └──► ManagerAlert
                                     🔴 RED (Line Stoppage / Breach)
```

- **🟢 GREEN:** Delivery is on schedule and warehouse stock exceeds safety thresholds.
- **🟡 YELLOW (Partial Fulfillment / Buffer Warning):** A delay or partial shipment occurred, but existing safety stock or a partial fallback order covers immediate assembly requirements while accruing SLA delay penalties.
- **🔴 RED (Critical Disruption):** Net available stock falls below required production quantities or delay exceeds the SLA grace window, placing the downstream `:Product` and `:ProductionProcess` at immediate risk.

---

## 4. LangGraph Multi-Agent & NLP Extraction Pipelines

### 4.1 Unstructured SLA Contract Extraction Pipeline (`services/llm_service.py` & `Data_Science/src/`)

Extracts structured contractual obligations from PDF, DOCX, or TXT agreements and converts them into RDF triples:

```
Upload Contract (PDF/DOCX/TXT)
       │
       ▼
┌──────────────┐   INVALID    ┌──────────────────────────────────────┐
│ 1. Guardrail │─────────────►│ Reject with HTTP 400 (Non-SLA Doc)   │
└──────┬───────┘              └──────────────────────────────────────┘
       │ VALID
       ▼
┌──────────────┐              ┌──────────────────────────────────────┐
│ 2. Extractor │─────────────►│ LLM .with_structured_output()        │
└──────┬───────┘              │ Extracts 11 SLA & Material Fields    │
       │                      └──────────────────┬───────────────────┘
       │                                         ▼
       │    Retry (≤ 3x with error feedback) ┌──────────────┐
       └─────────────────────────────────────┤ 3. Validator │
                                             └──────┬───────┘
                                                    │ VALID
                                                    ▼
                                      ┌───────────────────────────┐
                                      │ Side-by-Side Digital Twin │
                                      │ Diff & HITL Confirmation  │
                                      └─────────────┬─────────────┘
                                                    │
                                                    ▼
                                      ┌───────────────────────────┐
                                      │ SemanticLifter → SPARQL   │
                                      │ INSERT DATA into GraphDB  │
                                      └───────────────────────────┘
```

- **Semantic Business Rules Validated Automatically:**
  1. `sla_lead_time_hours` must be positive and `< 8760` hours (1 year), converted via the **Integer Day Rule** (`max(1, hours // 24)`).
  2. `minimum_quality_threshold` and `quality_penalty_rate` must be normalized decimals in `[0.0, 1.0]`.
  3. `delay_penalty_rate` and `missed_item_penalty_rate` must be non-negative financial rates.
  4. `supplier_id`, `supplier_name`, and `material` must be non-empty, sanitized identifiers.
- **Auto-Assembly Line Matching:** Upon upload, `/api/sandbox/match-assembly-line` checks GraphDB to automatically pre-select the impacted manufacturing line for known raw materials.

### 4.2 Real-Time Event-Driven Risk Engine (`services/risk_engine_service.py`)

```
IoT Telemetry Event ──► [ Node 1: fetch_sla ] ──► [ Node 2: analyze_risk ] ──► [ Node 3: generate_alert ]
(Delay / Weather /       Queries GraphDB for       LLM Risk Analyst combines    Routes alert to:
 Under-Shipment)         active SLA lead time,     telemetry + SLA terms →      • Procurement Manager
                         penalty rates, stock      RiskAnalysisResult           • Logistics Manager
                                                                                • Production Manager
```

### 4.3 Self-Correcting NL-to-SPARQL Chat Agent (`services/chat_service.py`)

```
User Question ──► [ Node 0: Guardrail ] ──(Off-Topic)──► Polite Domain Refusal
                         │
                      (Valid)
                         ▼
                  [ Node 1: SPARQL Developer ] ◄──(Syntax / Execution Error, Retry ≤ 3x)──┐
                         │                                                                │
                         ▼                                                                │
                  [ Node 2: GraphDB Executor ] ───────────────────────────────────────────┘
                         │
                     (Results)
                         ▼
                  [ Node 3: Customer Service ] ──► Concise Human-Readable Answer + Raw SPARQL
```

---

## 5. Machine Learning Delay Prediction & Supplier Scoring

The `Machine_Learning/` directory and corresponding backend services provide two production ML models and an automated supplier scoring engine:

### 5.1 Pre-Order Procurement Delay Classifier (`Machine_Learning/Procurement_Model/` & `services/order_risk_service.py`)
- **Algorithm:** `RandomForestClassifier(n_estimators=300, random_state=42, class_weight={0: 3, 1: 1})` with `StandardScaler`.
- **Feature Space:** **109 engineered features** (`Backend/models/ml_assets/model_features.json`) combining live GraphDB supplier metadata (reliability score, ESG score, historical delay rate, contracted lead time) with order specifics (quantity, unit price, PO type, department, seasonal/temporal encodings, and one-hot supplier/material encodings).
- **Output:** Predicts `on_time_probability` (`0.0–1.0`), classifies risk into `Low`, `Medium`, or `High`, estimates expected delay hours, and returns an explainability dictionary (`features_used`).

### 5.2 Real-Time Logistics Transit Delay Predictor (`Machine_Learning/Logistics_Model/` & `services/telemetry_simulator_service.py`)
- **Pipeline:** `ColumnTransformer` + `StandardScaler` + `SimpleImputer` regression pipeline (`delay_predictor_logistics.py` & `transit_delay_predictor.py`).
- **Live Telemetry Stream:** `telemetry_simulator_service.py` runs as a managed FastAPI background daemon (configurable via `TELEMETRY_INTERVAL_SECONDS`, default `30s`), reading GPS coordinates, vehicle speed, weather conditions, and traffic status to predict transit delay hours dynamically and push events through the Risk Engine.

### 5.3 Recency-Decay Supplier Reliability Evaluator (`services/supplier_evaluator_service.py`)
- Evaluates historical and newly placed purchase orders using an exponential recency-decay weight (`exp(-lambda * age)`), combining on-time delivery performance, quantity fulfillment accuracy, and price variance into an updated `:hasReliabilityScore` persisted directly in GraphDB.

---

## 6. React Frontend & Role-Based Control Tower

Located in `Frontend/my-app/`, the React 19 user interface provides a real-time operational control tower with **Role-Based Access Control (RBAC)**:

| Role | Primary Focus & Filtered KPIs |
|---|---|
| **Procurement Manager** | SLA contract uploads, side-by-side Digital Twin SLA diffing, supplier compliance violations, financial penalty tracking, fallback supplier assignment, pre-order ML risk prediction |
| **Logistics Manager** | Real-time IoT shipment delay alerts, transit disruption probabilities, route/weather delay diagnostics |
| **Production Manager** | Assembly line health (`GREEN` / `YELLOW` / `RED`), raw material inventory buffers, safety stock alerts, urgent fallback requests |
| **Admin** | Unfiltered executive view across all KPIs, suppliers, inventory risks, and system alerts |

### Key Application Pages (`Frontend/my-app/src/pages/`)
- **`Dashboard.jsx`**: Role-tailored KPI cards, supplier reliability charts, SLA violations table, and live risk panels.
- **`SLAUpload.jsx`**: Multi-format contract upload (PDF/DOCX/TXT), LLM extraction review, auto-matched assembly line selector, and **Live Digital Twin SLA Comparison** against existing active contracts in GraphDB.
- **`InventoryRisk.jsx`**: Material-level stock monitoring, `RED`/`YELLOW`/`GREEN` status indicators, assembly line mapping, and one-click backup supplier switching.
- **`Suppliers.jsx`**: Supplier reliability scorecards, historical transaction batch upload, and PO placement with live ML delay risk preview.
- **`SLAViolations.jsx` & `Alerts.jsx`**: Real-time feed of multi-agent alerts with read/dismiss lifecycle management and penalty calculations.
- **`ChatAssistant.jsx`**: Interactive NL-to-SPARQL chat interface with query inspection.

---

## 7. REST API Reference

When the backend is running, interactive Swagger UI documentation is available at **`http://localhost:8001/docs`** (and ReDoc at **`http://localhost:8001/redoc`**).

### 7.1 Sandbox & Ingestion Router (`/api/sandbox`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sandbox/upload-pdf` | Upload a PDF/DOCX/TXT contract → run 3-node LangGraph extraction → return `ExtractedSLAData` & mapped SLA for HITL review |
| `POST` | `/api/sandbox/confirm-sla` | Confirm human-reviewed SLA (`ConfirmedSLA`) → lift to RDF triples and persist in GraphDB |
| `POST` | `/api/sandbox/upload-sla` | Directly persist a structured `SLAContract` payload into GraphDB |
| `GET` | `/api/sandbox/match-assembly-line` | Auto-detect and return the linked production assembly line for a given material |
| `POST` | `/api/sandbox/simulate-iot` | Inject an `IoTTelemetryEvent` into the LangGraph Risk Engine and return a `ManagerAlert` |
| `POST` | `/api/sandbox/predict-order-risk` | Run the 109-feature Random Forest model to predict PO delay probability before order placement |
| `POST` | `/api/sandbox/place-order` | Place a purchase order, log the transaction, and trigger supplier reliability score updates |
| `POST` | `/api/sandbox/upload-transactions` | Upload an Excel/CSV procurement log to batch-recalculate supplier reliability scores in GraphDB |
| `POST` | `/api/sandbox/migrate-supplier-scores` | Initialize default reliability scores (`0.75`) for any suppliers missing a score in GraphDB |
| `GET` | `/api/sandbox/impacted-products` | Query OWL-inferred at-risk products and assembly lines from GraphDB |

### 7.2 Control Tower Dashboard Router (`/api/dashboard`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard/kpis` | Retrieve role-filtered executive KPIs (`?role=Procurement\|Logistics\|Production\|Admin`) |
| `GET` | `/api/dashboard/risk-scores` | Fetch all products and materials with `RED` / `YELLOW` / `GREEN` risk status and stock metrics |
| `GET` | `/api/dashboard/compliance-alerts` | Fetch active SLA contracts, lead times, grace periods, and compliance metrics |
| `GET` | `/api/dashboard/active-sla` | Retrieve the currently active SLA in GraphDB for side-by-side comparison during contract upload |
| `GET` | `/api/dashboard/fallback-options/{material_id}` | List ranked alternative/backup suppliers for a specific raw material |
| `POST` | `/api/dashboard/assign-fallback` | Switch a material's active supplier (or fulfill partial shortage) using a backup supplier |
| `POST` | `/api/dashboard/request-fallback` | Trigger a high-priority procurement alert requesting fallback sourcing for an at-risk material |
| `GET` | `/api/dashboard/assembly-lines` | List all manufacturing assembly lines / production processes in the ontology |
| `POST` | `/api/dashboard/assign-material-process` | Link a raw material to a specific assembly line in GraphDB |
| `GET` | `/api/dashboard/alerts` | Retrieve active role-targeted manager alerts generated by the Risk Engine |
| `POST` | `/api/dashboard/alerts/mark-read` | Mark a specific alert as `READ` |
| `POST` | `/api/dashboard/alerts/dismiss` | Dismiss an alert (`DISMISSED`) |
| `POST` | `/api/dashboard/chat` | Execute the 4-node NL-to-SPARQL conversational agent and return the answer + generated SPARQL |

---

## 8. Data Models & Schemas

Defined in [`Backend/models/schemas.py`](Backend/models/schemas.py) using **Pydantic v2**:

| Schema | Key Fields | Role in Pipeline |
|---|---|---|
| `ExtractedSLAData` | `document_id`, `supplier_id`, `supplier_name`, `material`, `sla_lead_time_hours`, `delay_penalty_rate`, `missed_item_penalty_rate`, `minimum_quality_threshold`, `quality_penalty_rate`, `quantity`, `unit_cost` | Structured output schema enforced on the LLM extractor node |
| `ConfirmedSLA` | `extraction_id`, `supplier_name`, `material`, `lead_time_days`, `penalty_clause`, `quantity`, `unit_cost`, `impacted_process`, `is_fallback`, penalty & quality rates | Human-in-the-Loop validated payload submitted from the UI |
| `SLAContract` | `supplier_name`, `material`, `lead_time_days`, `penalty_clause`, `quantity`, `unit_cost`, `impacted_process`, `is_fallback`, rate fields | Canonical domain model passed to `SemanticLifter` for RDF generation |
| `IoTTelemetryEvent` | `delivery_id`, `estimated_delay_hours`, `reason_code`, `disruption_probability`, `timestamp`, `quantity` | Real-time logistics event consumed by the LangGraph Risk Engine |
| `RiskAnalysisResult` | `risks`, `confidence`, `severity`, `financial_penalty_estimate`, `reasoning` | Structured LLM risk assessment output |
| `ManagerAlert` | `manager_title`, `alert_text`, `validated` | Role-routed operational alert persisted to GraphDB |
| `OrderRiskPredictionRequest` | `supplier_id`, `material_id`, `quantity`, `unit_price`, `po_date`, `po_type`, `department` | Input payload for pre-order ML delay risk evaluation |
| `OrderRiskPredictionResponse` | `status`, `on_time_probability`, `risk_level`, `estimated_delay_hours`, `features_used` | ML prediction output with feature explainability |

---

## 9. Resilience & Deterministic Fallback Strategy

The backend is engineered for **zero-downtime operation** even when external LLM APIs hit rate limits (`HTTP 429`) or when running in an offline evaluation environment:

1. **Thread-Safe `LLMClient` Singleton (`services/llm_service.py`):**
   - Uses double-checked locking to initialize the LLM client once.
   - Supports any OpenAI-compatible or Gemini endpoint via `LLM_API_KEY` / `LLM_BASE_URL` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY`.
2. **3-Stage Call Resilience (`Primary → 2x Retry → Deterministic Fallback`):**
   - If `LLM_FALLBACK_ENABLED=true` (default), quota exhaustion or missing API keys automatically degrade gracefully to deterministic domain-accurate simulation outputs for `ExtractedSLAData`, `RiskAnalysisResult`, and NL-to-SPARQL responses.
3. **GraphDB Mock Fallback:**
   - If GraphDB is unreachable during standalone sandbox testing, `risk_engine_service.py` falls back to baseline SLA parameters so agent pipelines remain testable end-to-end.

---

## 10. Monorepo Folder Structure

```text
semantic-digital-twin-backend/
├── LICENSE                                         # MIT License
├── README.md                                       # Comprehensive monorepo documentation
├── .gitignore                                      # Excludes .env, venv, .pkl binaries, raw CSV/XLSX lakes
│
├── Backend/                                        # FastAPI + LangGraph 3-Tier Backend
│   ├── main.py                                     # FastAPI entrypoint, CORS, telemetry lifecycle hooks
│   ├── requirements.txt                            # Pinned Python 3.12 dependencies
│   ├── api/                                        # Layer 1: HTTP Controllers (zero SPARQL/business logic)
│   │   ├── dashboard.py                            # 13 Control Tower & NL-to-SPARQL endpoints
│   │   └── sandbox.py                              # 10 SLA ingestion, HITL, IoT & ML prediction endpoints
│   ├── services/                                   # Layer 2: LangGraph Agents, ML Inference & Domain Logic
│   │   ├── llm_service.py                          # LLMClient singleton + 3-node SLA Extraction LangGraph
│   │   ├── lifting_service.py                      # SemanticLifter (Pydantic → RDF/SPARQL INSERT DATA)
│   │   ├── risk_engine_service.py                  # 3-node IoT Risk Engine & ManagerAlert router
│   │   ├── chat_service.py                         # 4-node self-correcting NL-to-SPARQL agent
│   │   ├── dashboard_service.py                    # SPARQL query wrappers, RBAC KPIs, fallback logic
│   │   ├── order_risk_service.py                   # 109-feature Random Forest PO delay risk predictor
│   │   ├── supplier_evaluator_service.py           # Recency-decay supplier reliability score calculator
│   │   └── telemetry_simulator_service.py          # Background IoT telemetry streamer + logistics ML model
│   ├── knowledge_base/                             # Layer 3: Ontotext GraphDB Data Access Layer
│   │   ├── connection.py                           # Stateless SPARQLWrapper singleton broker
│   │   └── repository.py                           # Named graphs, prefix enforcement, OWL inference queries
│   ├── models/                                     # Pydantic Schemas & ML Feature Definitions
│   │   ├── schemas.py                              # Strict Pydantic v2 request/response models
│   │   └── ml_assets/                              # Feature schema definitions for procurement & logistics ML
│   │       ├── model_features.json                 # 109-feature specification for PO delay classifier
│   │       └── logistics_model_features.json       # Feature specification for transit delay predictor
│   ├── scripts/                                    # Operational, Seeding, Simulation & Training Scripts
│   │   ├── generate_telemetry_stream.py            # Generates synthetic IoT logistics telemetry streams
│   │   ├── train_logistics_model.py                # Trains and serializes the logistics delay model
│   │   ├── inject_products.py                      # Seeds products and assembly line mappings into GraphDB
│   │   ├── inject_test_delay.py                    # Injects test delay scenarios (RED / YELLOW states)
│   │   ├── link_alt_supplier.py                    # Links backup suppliers to raw materials in GraphDB
│   │   ├── verify_model_loaded.py                  # Verifies ML model artifacts and feature alignment
│   │   └── verify_sla_rule.py                      # Verifies OWL SLA inference rules in GraphDB
│   ├── tests/                                      # Automated Unit, Integration & E2E Test Suites (11 suites)
│   │   ├── test_integration.py                     # 70-assertion core architecture & pipeline test suite
│   │   ├── test_graphdb_connection.py              # Live GraphDB triple insertion & OWL inference tests
│   │   ├── test_order_risk.py                      # Procurement ML classifier & 109-feature tests
│   │   ├── test_ml_backend_integration.py          # End-to-end ML + GraphDB integration tests
│   │   ├── test_supplierScore_updates.py           # Recency-decay supplier scoring tests
│   │   ├── test_fallback_e2e.py                    # Backup supplier switching & partial fulfillment E2E tests
│   │   ├── test_risk_scores.py                     # RED / YELLOW / GREEN status computation tests
│   │   └── test_chat_fallback.py                   # NL-to-SPARQL chat resilience tests
│   └── docs/
│       └── How to run.txt                          # Quick-reference startup guide
│
├── Data_Science/                                   # Ontology Engineering, Sample SLAs & Agent Prototypes
│   ├── ontology/
│   │   ├── Semantic Digital Twin Project.rdf       # Base OWL 2 supply chain ontology
│   │   ├── Semantic Digital Twin Project Inferred.rdf # Materialized OWL 2 inferred ontology graph
│   │   └── catalog-v001.xml                        # Protégé XML ontology catalog
│   ├── contracts/                                  # Sample Primary & Backup Supplier Contracts (PDF/DOCX/TXT)
│   │   ├── Acme Materials SLA.txt
│   │   ├── Acme_Doc.docx
│   │   ├── Acme_Test.pdf
│   │   ├── Apex_Motor_Backup.txt
│   │   ├── Aura_Steel_Backup.txt
│   │   ├── SLA_Global_Chemicals_Co.txt
│   │   ├── Steel_Supply_Backup.txt
│   │   └── TechChem European Supply Agreement.txt
│   └── src/                                        # Standalone Data Science Agent Modules
│       ├── SLA Extractor (Tool Use) v3.py          # Standalone LangGraph SLA extraction prototype
│       ├── impact_mitigation_agents_v3.py          # Standalone multi-agent impact mitigation prototype
│       ├── chat_v2.py                              # Standalone NL-to-SPARQL conversational agent
│       └── data_loader.py                          # Ontology and RDF bulk data loader
│
├── Machine_Learning/                               # Model Training Notebooks & Standalone Predictors
│   ├── Procurement_Model/
│   │   ├── Graduation_Project_final.ipynb          # Procurement delay classifier training notebook
│   │   ├── Supplier_Score.ipynb                    # Supplier reliability scoring research notebook
│   │   ├── procurement_delay_predictor.py          # RandomForestClassifier training & inference module
│   │   ├── seed_procurement_evaluation.py          # GraphDB evaluation context seeder for procurement
│   │   └── model_features.json                     # 109 engineered procurement features
│   └── Logistics_Model/
│       ├── Delay_orediction.ipynb                  # Logistics transit delay research notebook
│       ├── delay_predictor_logistics.py            # Transit delay pipeline training script
│       ├── transit_delay_predictor.py              # Real-time transit delay inference module
│       ├── seed_evaluation_context.py              # Logistics evaluation context seeder
│       └── logistics_features.json                 # Logistics model feature specification
│
└── Frontend/                                       # React 19 Supply Chain Control Tower
    ├── package.json                                # Root wrapper scripts (start, build, test, install)
    └── my-app/                                     # React application workspace
        ├── package.json                            # React 19.2 dependencies
        ├── public/                                 # Static assets
        └── src/
            ├── App.js                              # Application router & RBAC state provider
            ├── auth/roles.js                       # Role definitions (Procurement, Logistics, Production, Admin)
            ├── components/
            │   ├── dashboard/                      # KPISection, ReliabilityChart, RiskPanel, SLAViolationsTable
            │   └── layout/                         # Layout, Sidebar, Topbar (with role switcher & alert bell)
            ├── pages/                              # Dashboard, SLAUpload, SLAViolations, InventoryRisk,
            │                                       # Suppliers, Alerts, ChatAssistant, Login
            ├── services/api.js                     # REST API client connecting to FastAPI (Port 8001)
            └── styles/                             # Theme tokens & dashboard CSS
```

---

## 11. Local Setup & Installation

### Prerequisites

- **Python** `3.12+`
- **Node.js** `18+` and **npm** (for the React Control Tower frontend)
- **Ontotext GraphDB** `10.x+` running locally on port `7200` (optional for offline fallback testing; required for live SPARQL persistence and OWL reasoning)

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/YousefOsamaMahmoud/semantic-digital-twin-backend.git
cd semantic-digital-twin-backend
```

---

### Step 2: Configure Ontotext GraphDB (Knowledge Graph)

1. Start **Ontotext GraphDB** (default: `http://localhost:7200`).
2. Create a new repository (e.g., `supply-chain` or `SLA_DigitalTwin`) with **OWL-Horst (Optimized)** or **OWL2-RL** ruleset enabled.
3. Import the base ontology file [`Data_Science/ontology/Semantic Digital Twin Project.rdf`](Data_Science/ontology/Semantic%20Digital%20Twin%20Project.rdf) into the repository (target graph `<http://example.org/ontology/>`).

---

### Step 3: Set Up the FastAPI Backend

```bash
# Create and activate a virtual environment
python -m venv venv

# Windows (PowerShell / CMD)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install pinned backend dependencies
cd Backend
pip install -r requirements.txt
```

Create a `Backend/.env` file with your local configuration:

```env
# ─── Ontotext GraphDB Configuration ──────────────────────────────────────────
GRAPHDB_URL=http://localhost:7200
GRAPHDB_REPO=supply-chain
GRAPHDB_USER=
GRAPHDB_PASSWORD=

# ─── LLM / NLP Pipeline Configuration (Gemini / OpenRouter / OpenAI) ─────────
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=your-api-key-here
LLM_FALLBACK_ENABLED=true

# ─── Background IoT Telemetry Simulator ──────────────────────────────────────
TELEMETRY_INTERVAL_SECONDS=30
```

> **Note:** Setting `LLM_FALLBACK_ENABLED=true` allows the entire backend to run and pass all integration tests even without a live external LLM API key.

#### Train / Generate Local ML Artifacts (First-Time Setup)

Because `.pkl` binary artifacts are excluded via `.gitignore`, generate the local model binaries before starting the server if testing live ML predictions:

```bash
# From the Backend/ directory
python scripts/train_logistics_model.py
python ../Machine_Learning/Procurement_Model/procurement_delay_predictor.py
```

#### Start the FastAPI Server

```bash
cd Backend
uvicorn main:app --reload --port 8001
```

- **API Health Check:** [http://localhost:8001/](http://localhost:8001/)
- **Interactive Swagger UI:** [http://localhost:8001/docs](http://localhost:8001/docs)

---

### Step 4: Set Up & Launch the React Control Tower Frontend

Open a second terminal window:

```bash
cd Frontend/my-app
npm install
npm start
```

The Control Tower UI will launch at **[http://localhost:3000](http://localhost:3000)** and automatically connect to the FastAPI backend on `http://localhost:8001`.

---

## 12. Testing & Verification

Run the automated test suites from the `Backend/` directory:

```bash
cd Backend

# 1. Core 70-Assertion Integration Suite (Pydantic schemas, LangGraph topologies,
#    SemanticLifter namespace guards, SPARQL escaping, LLM fallback resilience)
python -m tests.test_integration

# 2. Live GraphDB Connection & OWL 2 Inference Verification
python -m tests.test_graphdb_connection

# 3. Pre-Order ML Risk Classifier & 109-Feature Pipeline Verification
python -m tests.test_order_risk

# 4. ML + Backend End-to-End Integration Suite
python -m tests.test_ml_backend_integration

# 5. Dynamic Supplier Reliability Score Recalculation Suite
python -m tests.test_supplierScore_updates

# 6. Primary-to-Backup Supplier Fallback & Partial Fulfillment E2E Suite
python -m tests.test_fallback_e2e
```

---

## License

Distributed under the **MIT License**. See [`LICENSE`](./LICENSE) for full details.

**Copyright (c) 2026 Yousef Osama Mahmoud**
