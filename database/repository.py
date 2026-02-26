# ============================================================
# database/repository.py — Layer 3: Graph Repository
#
# This module contains functions that build and execute
# Cypher queries against Neo4j. It knows NOTHING about HTTP
# or the web framework — it only talks to the database.
#
# Each function should:
#   1. Accept plain Python objects (or Pydantic models).
#   2. Build a parameterised Cypher query.
#   3. Call db.execute_write() / db.execute_read().
#   4. Return a simple dict with the results.
# ============================================================

from database.connection import db
from models.schemas import SLAContract


def create_contract_graph(contract: SLAContract) -> dict:
    """
    Persist an SLA contract as a small sub-graph in Neo4j.

    Graph pattern created
    ---------------------
        (:Supplier {name})
              |
        [:SUPPLIES {lead_time_days, penalty_clause}]
              |
              v
        (:RawMaterial {name})

    We use MERGE instead of CREATE so that:
      - If the Supplier already exists, we reuse it.
      - If the RawMaterial already exists, we reuse it.
      - If the relationship already exists, we update its
        properties rather than creating a duplicate edge.

    Parameters
    ----------
    contract : SLAContract
        The validated Pydantic model coming from the API layer.

    Returns
    -------
    dict
        A confirmation dict with the supplier and material names.
    """

    # ----------------------------------------------------------
    # Cypher query — heavily commented for learning purposes
    # ----------------------------------------------------------
    cypher_query = """
    // ── Step 1: Find or create the Supplier node ──
    // MERGE acts like "get-or-create":
    //   • If a (:Supplier {name: $supplier_name}) already
    //     exists, Neo4j binds it to the variable `s`.
    //   • If it does NOT exist, Neo4j creates it first.
    MERGE (s:Supplier {name: $supplier_name})

    // ── Step 2: Find or create the RawMaterial node ──
    // Same logic — avoids duplicate material nodes.
    MERGE (m:RawMaterial {name: $material_name})

    // ── Step 3: Find or create the SUPPLIES relationship ──
    // This ties the Supplier to the RawMaterial.
    // We match on the two endpoints so that the
    // relationship is unique per (Supplier, Material) pair.
    MERGE (s)-[r:SUPPLIES]->(m)

    // ── Step 4: Set / update relationship properties ──
    // ON CREATE SET  → runs only when the edge is brand-new.
    // ON MATCH SET   → runs when the edge already existed
    //                  (i.e. the SLA was re-uploaded / updated).
    ON CREATE SET r.lead_time_days  = $lead_time_days,
                  r.penalty_clause  = $penalty_clause
    ON MATCH  SET r.lead_time_days  = $lead_time_days,
                  r.penalty_clause  = $penalty_clause

    // ── Step 5: Return confirmation data ──
    RETURN s.name AS supplier, m.name AS material
    """

    # ----------------------------------------------------------
    # Parameter map — values are safely injected by the driver
    # (no string concatenation → no Cypher-injection risk).
    # ----------------------------------------------------------
    parameters = {
        "supplier_name": contract.supplier_name,
        "material_name": contract.material,
        "lead_time_days": contract.lead_time_days,
        "penalty_clause": contract.penalty_clause,
    }

    # Run the write transaction and grab the first record
    result = db.execute_write(cypher_query, parameters)

    # result is a list of dicts, e.g.:
    # [{"supplier": "Acme Steel Corp", "material": "Cold-Rolled Steel"}]
    return {
        "supplier": result[0]["supplier"],
        "material": result[0]["material"],
    }
