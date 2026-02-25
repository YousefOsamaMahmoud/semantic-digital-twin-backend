# SLA Sandbox Feature: Full Documentation & Explanation

Project: **Semantic Digital Twin for Raw Material Supply Detection and Resolution**

This document provides a detailed breakdown of the backend structure, code logic, and data models implemented for the **SLA Sandbox** skeleton.

---

## 1. Project Architecture (The 3-Tier Pattern)

To ensure scalability and maintain clean code, the project strictly follows a **3-Tier Layered Architecture**. Each layer has a specific responsibility:

1.  **Layer 1: API / Controller (`api/`)**
    *   **Role:** The "Entry Point." It handles incoming web requests from the frontend.
    *   **Logic:** It validates the data coming in and sends back a response. It does **not** perform calculations or database operations.
    *   **File:** `api/sandbox.py`

2.  **Layer 2: Service Layer (`services/`)**
    *   **Role:** The "Brain." This is where the business logic lives (e.g., LLM extraction scripts, AI model predictions).
    *   **Logic:** It processes data received from the API layer and prepares it for storage or analysis.
    *   **Current State:** Skeleton initialized (ready for future AI integration).

3.  **Layer 3: Database / Repository Layer (`database/`)**
    *   **Role:** The "Broker." It is the only layer allowed to talk directly to the Neo4j database.
    *   **Logic:** It executes Cypher queries to save or retrieve nodes and relationships.
    *   **Current State:** Skeleton initialized (ready for Neo4j connection logic).

---

## 2. Data Models (Schemas)

We use **Pydantic** to define our data structures. This ensures that every piece of data entering the system is correctly formatted.

**File:** `models/schemas.py`

### `SLAContract` Model
This model represents the structured data extracted from a PDF contract.

| Field | Type | Description | Validation Rule |
| :--- | :--- | :--- | :--- |
| `supplier_name` | `str` | Name of the supplier | At least 1 character |
| `material` | `str` | Type of raw material | At least 1 character |
| `lead_time_days` | `int` | Delivery promise in days | Must be greater than 0 |
| `penalty_clause` | `str` | Text describing the fine | At least 1 character |

**Why Pydantic?**
If a user tries to send a negative number for `lead_time_days` or leaves the `supplier_name` empty, FastAPI will automatically block the request and return a clear error message before the code even tries to process it.

---

## 3. API Endpoints

### root GET (`/`)
*   **File:** `main.py`
*   **Function:** `read_root()`
*   **Description:** A simple health check. It confirms the server is running correctly.
*   **Response:** `{"message": "Hello Cavengers! The Backend is alive!"}`

### SLA Sandbox POST (`/api/sandbox/upload-sla`)
*   **File:** `api/sandbox.py`
*   **Function:** `upload_sla(contract: SLAContract)`
*   **Description:** This is the entry point for the Sandbox feature. It receives the contract data, validates it against the `SLAContract` schema, and echoes it back to confirm success.
*   **Flow:** Frontend sends JSON $\rightarrow$ API Layer validates it $\rightarrow$ API Layer returns success and the data.

---

## 4. Why the `__init__.py` files?

In Python, folders like `api/` and `services/` aren't automatically seen as "packages." By adding an empty `__init__.py` file to each folder, we tell Python: *"Treat this folder as a module so I can import code from it."*

This allows us to do things like:
`from api.sandbox import router` in our `main.py`.

---

## 5. How to Run & Troubleshooting

### Standard Command:
Inside your virtual environment (`venv`), run:
```bash
uvicorn main:app --reload
```

### Common Error: `[WinError 10013]` (Socket Permission)
If you see this error, it means the port (usually 8000) is either:
1.  Already in use by another program.
2.  Blocked by your Windows Firewall or access permissions.

**Solution:** Run on a different port using the `--port` flag:
```bash
uvicorn main:app --reload --port 8001
```

---

## 6. Next Steps
1.  **Integrate LLM:** Move PDF extraction logic into `services/`.
2.  **Connect Neo4j:** Write the database broker in `database/`.
3.  **Semantic Lifting:** Transform the validated JSON into RDF triples to save into the Graph.
