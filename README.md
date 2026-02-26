

### Step 1: Copy this perfectly formatted Markdown

**Important:** Do not just highlight the text with your mouse. Look at the top right corner of the black box below. You will see a little **"Copy code"** button. Click that button to grab the raw text perfectly!

```markdown
# SLA Sandbox Feature: Full Documentation & Explanation

Project: **Semantic Digital Twin for Raw Material Supply Detection and Resolution**

This document provides a detailed breakdown of the backend structure, code logic, and data models implemented for the **SLA Sandbox** skeleton and Neo4j Database integration.

---

## 1. Project Architecture (The 3-Tier Pattern)

To ensure scalability and maintain clean code, the project strictly follows a **3-Tier Layered Architecture**. Each layer has a specific responsibility:

1.  **Layer 1: API / Controller (`api/`)**
    * **Role:** The "Entry Point." It handles incoming web requests from the frontend.
    * **Logic:** It validates the data coming in and sends back a response. It does **not** perform calculations or database operations.
    * **File:** `api/sandbox.py`

2.  **Layer 2: Service Layer (`services/`)**
    * **Role:** The "Brain." This is where the business logic lives (e.g., LLM extraction scripts, AI model predictions).
    * **Logic:** It processes data received from the API layer and prepares it for storage or analysis.
    * **Current State:** Skeleton initialized (ready for future AI integration).

3.  **Layer 3: Database / Repository Layer (`database/`)**
    * **Role:** The "Broker." It is the only layer allowed to talk directly to the Neo4j database.
    * **Logic:** It executes Cypher queries to save or retrieve nodes and relationships via AuraDB.
    * **Current State:** Fully implemented with `python-dotenv` and the `neo4j` Python driver.

---

## 2. Neo4j Database Layer (Layer 3 Walkthrough)

### What Was Built
| File | Purpose |
| :--- | :--- |
| `connection.py` | `Neo4jConnection` class — singleton driver, `execute_write()` helper. Securely loads AuraDB credentials via `.env`. |
| `repository.py` | `create_contract_graph()` — MERGE-based Cypher query to insert data. |
| `sandbox.py` | Updated endpoint (`/api/sandbox/upload-sla`) — calls repository, returns graph confirmation. |
| `main.py` | Added `shutdown` event to close the Neo4j driver cleanly. |

### Data Flow
1. **POST** `/api/sandbox/upload-sla` (JSON body)
2. `api/sandbox.py` $\rightarrow$ validates payload (Pydantic)
3. `database/repository.py` $\rightarrow$ builds Cypher, calls `execute_write()`
4. `database/connection.py` $\rightarrow$ opens Neo4j session, runs transaction securely via AuraDB
5. **Neo4j Graph:** `(Supplier)-[:SUPPLIES]->(RawMaterial)`

### Graph Pattern Created
```cypher
(:Supplier {name: "Stark Industries"})
    -[:SUPPLIES {lead_time_days: 14, penalty_clause: "2% per day"}]->
(:RawMaterial {name: "Cold-Rolled Steel"})

```

*Note: Uses `MERGE` ensuring idempotency; re-uploading the same supplier/material updates properties instead of creating duplicates.*

---

## 3. Data Models (Schemas)

We use **Pydantic** to define our data structures. This ensures that every piece of data entering the system is correctly formatted.

**File:** `models/schemas.py`

### `SLAContract` Model

This model represents the structured data extracted from a PDF contract.

| Field | Type | Description | Validation Rule |
| --- | --- | --- | --- |
| `supplier_name` | `str` | Name of the supplier | At least 1 character |
| `material` | `str` | Type of raw material | At least 1 character |
| `lead_time_days` | `int` | Delivery promise in days | Must be greater than 0 |
| `penalty_clause` | `str` | Text describing the fine | At least 1 character |

---

## 4. API Endpoints

### Root GET (`/`)

* **File:** `main.py`
* **Description:** A simple health check. Confirms the server is running.
* **Response:** `{"message": "Hello Cavengers! The Backend is alive!"}`

### SLA Sandbox POST (`/api/sandbox/upload-sla`)

* **File:** `api/sandbox.py`
* **Description:** Receives the contract data, validates it, and triggers the database repository to securely build the graph in AuraDB.

---

## 5. Why the `__init__.py` files?

In Python, folders like `api/` and `services/` aren't automatically seen as "packages." By adding an empty `__init__.py` file to each folder, we tell Python: *"Treat this folder as a module so I can import code from it."*

---

## 6. How to Run, Test & Troubleshoot

### 1. Configure Environment Variables

Ensure you have a `.env` file in the root directory (ignored by Git) containing your Neo4j AuraDB credentials:

```text
NEO4J_URI=neo4j+s://[your-id].databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password

```

### 2. Start the Server

Inside your virtual environment (`venv`), run:

```bash
uvicorn main:app --reload --port 8001

```

*(Note: We use port 8001 to avoid common Windows `[WinError 10013]` Socket Permission errors on port 8000).*

### 3. Test via Swagger UI

Open `http://127.0.0.1:8001/docs` $\rightarrow$ **POST** `/api/sandbox/upload-sla` with:

```json
{
  "supplier_name": "Stark Industries",
  "material": "Cold-Rolled Steel",
  "lead_time_days": 14,
  "penalty_clause": "2% deduction per day of delay"
}

```

### 4. Verify in Neo4j AuraDB Workspace

Open your Aura console and run:

```cypher
MATCH (s:Supplier)-[r:SUPPLIES]->(m:RawMaterial) RETURN s, r, m

```

---

## 7. Next Steps

1. **Integrate LLM (Layer 2):** Move PDF extraction logic into `services/` to replace hardcoded JSON payloads.
2. **Expand the Graph:** Add Factory, Product, and Customer nodes to simulate a full supply chain.



