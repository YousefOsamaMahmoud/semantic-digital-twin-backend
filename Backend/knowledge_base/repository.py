# ============================================================
# database/repository.py — Layer 3: SPARQL Graph Repository
#
# This module contains functions that build and execute
# SPARQL queries against GraphDB.  It knows NOTHING about
# HTTP or the web framework — it only talks to the database.
#
# ╔══════════════════════════════════════════════════════════╗
# ║  GOLDEN RULE #2 — NAMESPACE CONSISTENCY                  ║
# ║  Every triple inserted by the LLM must use the SAME      ║
# ║  namespace prefix as the OWL ontology file.               ║
# ║  Our ontology defines:                                    ║
# ║    PREFIX : <http://example.org/ontology#>                ║
# ║  So ALL individuals and predicates must live under that   ║
# ║  same namespace.  If the LLM outputs "ex:Supplier",      ║
# ║  re-map it to ":Supplier" before insertion.               ║
# ╚══════════════════════════════════════════════════════════╝
# ============================================================

from knowledge_base.connection import graphdb
from models.schemas import SLAContract

# ---- Shared Namespace Prefix Block ----
# This prefix block is prepended to every SPARQL query to
# guarantee namespace consistency across the whole system.
PREFIXES = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# ---- Named Graph URIs ----
# GOLDEN RULE — Named Graph Separation:
#   Ontology rules  → loaded into  http://example.org/ontology/
#   Contract data   → inserted into http://example.org/contracts/
# This keeps your OWL axioms separate from instance data.
CONTRACT_GRAPH = "http://example.org/contracts/"


def _sanitize_uri_fragment(name: str) -> str:
    """
    Convert a human-readable name into a safe URI fragment.

    Examples
    --------
    >>> _sanitize_uri_fragment("Stark Industries")
    'Stark_Industries'
    >>> _sanitize_uri_fragment("Cold-Rolled Steel")
    'Cold-Rolled_Steel'
    """
    return name.strip().replace(" ", "_")


def create_contract_graph(contract: SLAContract) -> dict:
    """
    Persist an SLA contract as RDF triples in GraphDB.

    Graph pattern created (in Named Graph <http://example.org/contracts/>)
    -----------------------------------------------------------------------
        :Stark_Industries  rdf:type       :Supplier .
        :Cold-Rolled_Steel rdf:type       :RawMaterial .
        :Stark_Industries  :supplies      :Cold-Rolled_Steel .
        :Stark_Industries  :leadTimeDays  14 .
        :Stark_Industries  :penaltyClause "2% per day" .

    Parameters
    ----------
    contract : SLAContract
        The validated Pydantic model coming from the API layer.

    Returns
    -------
    dict
        A confirmation dict with the supplier and material names.
    """

    # ---- Build safe URI fragments ----
    supplier_uri = _sanitize_uri_fragment(contract.supplier_name)
    material_uri = _sanitize_uri_fragment(contract.material)

    # ---- SPARQL UPDATE query ----
    # We use INSERT DATA to add triples into the contracts
    # Named Graph.  All URIs use the ontology namespace (:)
    # to satisfy Golden Rule #2 (Namespace Consistency).
    sparql_update = f"""
    {PREFIXES}

    INSERT DATA {{
        GRAPH <{CONTRACT_GRAPH}> {{

            # ── Supplier individual ──
            :{supplier_uri}  rdf:type       :Supplier ;
                             rdfs:label     "{contract.supplier_name}" .

            # ── RawMaterial individual ──
            :{material_uri}  rdf:type       :RawMaterial ;
                             rdfs:label     "{contract.material}" .

            # ── Relationship: Supplier supplies RawMaterial ──
            :{supplier_uri}  :supplies      :{material_uri} .

            # ── SLA Properties on the Supplier ──
            :{supplier_uri}  :leadTimeDays  {contract.lead_time_days} .
            :{supplier_uri}  :penaltyClause "{contract.penalty_clause}" .
        }}
    }}
    """

    # Execute the update (stateless HTTP POST to GraphDB)
    graphdb.execute_sparql_update(sparql_update)

    return {
        "supplier": contract.supplier_name,
        "material": contract.material,
        "graph": CONTRACT_GRAPH,
        "message": "Triples inserted successfully into GraphDB.",
    }


def find_impacted_products_by_supplier_delay() -> list[dict]:
    """
    SPARQL SELECT that demonstrates OWL Inference.

    This query finds all Products that are "At Risk" because
    a Supplier has a delay.  The key point is that the
    :isAtRisk property is NOT explicitly stored in the data.
    Instead, GraphDB's OWL reasoning engine infers it from
    rules defined in the ontology, such as:

        If a :Supplier :hasDelay true
        AND that :Supplier :supplies a :RawMaterial
        AND a :Product :requires that :RawMaterial
        THEN that :Product :isAtRisk true

    Returns
    -------
    list[dict]
        Each dict contains the product name and risk status.
    """

    sparql_query = f"""
    {PREFIXES}

    SELECT ?supplierLabel ?materialLabel ?productLabel ?riskStatus
    WHERE {{
        # ── Find suppliers that have declared a delay ──
        ?supplier  rdf:type     :Supplier ;
                   rdfs:label   ?supplierLabel ;
                   :hasDelay    true .

        # ── Find what material that supplier provides ──
        ?supplier  :supplies    ?material .
        ?material  rdfs:label   ?materialLabel .

        # ── Find products that require that material ──
        ?product   rdf:type     :Product ;
                   rdfs:label   ?productLabel ;
                   :requires    ?material .

        # ── This triple is INFERRED by GraphDB's OWL reasoner ──
        # It should NOT exist as explicit data; the reasoner
        # derives it from the ontology axioms above.
        ?product   :isAtRisk    ?riskStatus .
    }}
    ORDER BY ?productLabel
    """

    return graphdb.execute_sparql_select(sparql_query)
