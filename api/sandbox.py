# ============================================================
# api/sandbox.py — Layer 1: Controller / API Router
#
# This module defines the SLA Sandbox endpoints.
# It is ONLY responsible for:
#   1. Receiving the HTTP request
#   2. Validating the payload (via Pydantic)
#   3. Calling the database layer to persist data
#   4. Returning the HTTP response
#
# It contains ZERO business logic — that will live in
# services/ once we wire up the LLM extraction pipeline.
# ============================================================

from fastapi import APIRouter, HTTPException
from models.schemas import SLAContract
from database.repository import create_contract_graph

# Create a dedicated router for all /sandbox endpoints.
# The prefix means every route below is automatically
# served under /api/sandbox/...
router = APIRouter(
    prefix="/api/sandbox",
    tags=["SLA Sandbox"],  # Groups these endpoints in the Swagger UI
)


@router.post("/upload-sla")
def upload_sla(contract: SLAContract):
    """
    **POST /api/sandbox/upload-sla**

    Accepts a validated SLA contract payload, saves it to the
    Neo4j knowledge graph, and returns a confirmation message.

    Graph pattern created
    ---------------------
        (:Supplier) -[:SUPPLIES {lead_time, penalty}]-> (:RawMaterial)

    Errors
    ------
    500  If Neo4j is unreachable or the write transaction fails.
    422  If the JSON payload fails Pydantic validation (automatic).
    """
    try:
        # ---- Persist to Neo4j (Layer 3) ----
        graph_result = create_contract_graph(contract)

        return {
            "status": "success",
            "message": (
                f"SLA contract saved to the knowledge graph. "
                f"Created/updated: ({graph_result['supplier']})"
                f"-[:SUPPLIES]->({graph_result['material']})"
            ),
            "graph_data": graph_result,
        }

    except Exception as e:
        # Surface a clear error so the frontend knows what
        # went wrong without leaking internal stack traces.
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to save SLA contract to Neo4j. "
                f"Reason: {str(e)}"
            ),
        )
