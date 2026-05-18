# ============================================================
# services/lifting_service.py — Layer 2: Semantic Lifting
#
# Responsible for converting validated Pydantic models into
# valid SPARQL INSERT DATA statements using the project's
# strict ontology namespace.
#
# ╔══════════════════════════════════════════════════════════╗
# ║  NAMESPACE ENFORCEMENT BOUNDARY                          ║
# ║                                                          ║
# ║  Every SPARQL statement produced by this module MUST     ║
# ║  use  PREFIX : <http://example.org/ontology#>            ║
# ║                                                          ║
# ║  The data science team's temporary namespace             ║
# ║  (http://www.semanticweb.org/youssef/ontologies/...)     ║
# ║  is STRICTLY FORBIDDEN in files written here.            ║
# ╚══════════════════════════════════════════════════════════╝
# ============================================================

import logging
import re
from typing import Any

from knowledge_base.connection import graphdb
from knowledge_base.repository import (
    CONTRACT_GRAPH,
    PREFIXES,
    _sanitize_uri_fragment,
    create_contract_graph,
)
from models.schemas import ConfirmedSLA, ExtractedSLAData, SLAContract

logger = logging.getLogger(__name__)


# ==============================================================
# 1. STRING ESCAPING FOR SPARQL LITERALS
# ==============================================================


def _escape_sparql_literal(value: str) -> str:
    """
    Escape a string value for safe use inside a SPARQL quoted literal.

    SPARQL string literals are delimited by double quotes.  If the
    value itself contains double quotes, backslashes, or newlines
    the query will break.  This function escapes those characters.

    Examples
    --------
    >>> _escape_sparql_literal('2% deduction per day of delay')
    '2% deduction per day of delay'
    >>> _escape_sparql_literal('Penalty: "$500" per day')
    'Penalty: \\"$500\\" per day'
    """
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("\r", "\\r")
    return escaped


def _build_contract_id(document_id: str) -> str:
    """
    Convert a document ID into a safe URI fragment for a contract.

    Removes or replaces characters that are invalid in SPARQL
    local name segments.

    Examples
    --------
    >>> _build_contract_id("SLA-ACME-2026-V2")
    'SLA_ACME_2026_V2'
    >>> _build_contract_id("EXT-A1B2C3D4E5F6")
    'EXT_A1B2C3D4E5F6'
    """
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", document_id)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe if safe else f"Contract_{abs(hash(document_id))}"


def _build_supplier_uri(supplier_id: str, supplier_name: str) -> str:
    """
    Build a URI-safe supplier identifier, preferring the ID when
    available and falling back to the sanitised name.

    The result is intended to be used as ``:Supplier_{fragment}``.

    Examples
    --------
    >>> _build_supplier_uri("SUP_001", "Acme Corp")
    'Supplier_SUP_001'
    >>> _build_supplier_uri("", "Acme Corp")
    'Supplier_Acme_Corp'
    """
    if supplier_id and supplier_id.strip():
        safe = _sanitize_uri_fragment(supplier_id)
        if not safe.startswith("Supplier_"):
            safe = f"Supplier_{safe}"
        return safe
    return f"Supplier_{_sanitize_uri_fragment(supplier_name)}"


def _build_material_uri(material: str) -> str:
    """
    Build a URI-safe material identifier with fallback.
    """
    safe = _sanitize_uri_fragment(material)
    return safe if safe else f"Material_{abs(hash(material))}"


# ==============================================================
# 2. SEMANTIC LIFTER
# ==============================================================


class SemanticLifter:
    """
    Converts validated Pydantic models into SPARQL INSERT DATA
    statements and, where appropriate, persists them to GraphDB.

    This class is the **exclusive** bridge between the service
    layer (Pydantic) and the database layer (RDF triples).  No
    other module should be generating SPARQL INSERT strings
    against the ``http://example.org/contracts/`` named graph.

    Usage
    -----
    >>> lifter = SemanticLifter()
    >>> sparql = lifter.lift_extracted_data(extracted)
    >>> result = lifter.persist_confirmed_sla(confirmed)
    """

    # ----------------------------------------------------------
    # Hours-to-days conversion (Integer Day Rule)
    # ----------------------------------------------------------

    @staticmethod
    def _hours_to_days(hours: int) -> int:
        """
        Convert an SLA lead time from hours to whole days.

        **Integer Day Rule**

        - ``hours // 24`` — integer division, no rounding.
        - If ``hours < 24`` the result is 0, which would violate
          the ``gt=0`` constraint on ``SLAContract.lead_time_days``.
          In that case we default to **1** day so the ontology
          boundary remains structurally valid.

        Parameters
        ----------
        hours : int
            Lead time in hours (from the LLM extraction).

        Returns
        -------
        int
            Lead time in days, minimum 1.
        """
        days = hours // 24
        return days if days >= 1 else 1

    # ----------------------------------------------------------
    # ExtractedData → SPARQL INSERT DATA
    # ----------------------------------------------------------

    def lift_extracted_data(self, data: ExtractedSLAData) -> str:
        """
        Convert an ``ExtractedSLAData`` Pydantic model into a raw
        SPARQL INSERT DATA statement.

        The generated triples model:

        - A ``:Supplier`` individual (from supplier_id / supplier_name)
        - A ``:RawMaterial`` individual (from material)
        - A ``:SLAContract`` individual (from document_id)
        - ``:supplies`` — Supplier provides the Material
        - ``:hasSupplier`` — Contract is linked to the Supplier
        - SLA parameters (lead time, penalty rates, quality
          thresholds) as data properties on the Contract

        All URIs use the project's strict ontology namespace
        ``<http://example.org/ontology#>``.

        Parameters
        ----------
        data : ExtractedSLAData
            The validated, LLM-extracted SLA fields.

        Returns
        -------
        str
            A complete SPARQL INSERT DATA query ready to execute.
        """
        document_uri = _build_contract_id(data.document_id)
        supplier_uri = _build_supplier_uri(data.supplier_id, data.supplier_name)
        material_uri = _build_material_uri(data.material)

        lead_days = self._hours_to_days(data.sla_lead_time_hours)

        penalty_clause = (
            f"Delay penalty: ${_escape_sparql_literal(str(data.delay_penalty_rate))}/day. "
            f"Missed item penalty: ${_escape_sparql_literal(str(data.missed_item_penalty_rate))}/unit. "
            f"Quality penalty: {_escape_sparql_literal(str(data.quality_penalty_rate * 100))}% of order value."
        )

        sparql = f"""{PREFIXES}

INSERT DATA {{
    GRAPH <{CONTRACT_GRAPH}> {{

        # ── Supplier ──
        :{supplier_uri}  rdf:type       :Supplier ;
                         rdfs:label     "{_escape_sparql_literal(data.supplier_name)}" .

        # ── Raw Material ──
        :{material_uri}  rdf:type       :RawMaterial ;
                          rdfs:label     "{_escape_sparql_literal(data.material)}" .

        # ── Supplier supplies Material ──
        :{supplier_uri}  :supplies      :{material_uri} .

        # ── SLA Contract ──
        :{document_uri}  rdf:type            :SLAContract ;
                         :hasSupplier        :{supplier_uri} ;
                         :governsMaterial    :{material_uri} ;
                         :leadTimeDays       {lead_days} ;
                         :penaltyClause      "{_escape_sparql_literal(penalty_clause)}" ;
                         :hasSLALeadTime     "{data.sla_lead_time_hours}"^^xsd:integer ;
                         :hasDelayPenaltyRate "{data.delay_penalty_rate}"^^xsd:decimal ;
                         :hasMissedItemPenaltyRate "{data.missed_item_penalty_rate}"^^xsd:decimal ;
                         :hasMinimumQualityThreshold "{data.minimum_quality_threshold}"^^xsd:decimal ;
                         :hasQualityPenaltyRate "{data.quality_penalty_rate}"^^xsd:decimal .
    }}
}}
"""
        logger.info(
            "Lifted ExtractedSLAData(doc=%s, supplier=%s) to SPARQL.",
            document_uri,
            supplier_uri,
        )
        return sparql

    # ----------------------------------------------------------
    # ExtractedData → SLAContract (business summary)
    # ----------------------------------------------------------

    def to_sla_contract(self, data: ExtractedSLAData) -> SLAContract:
        """
        Build an ``SLAContract`` from ``ExtractedSLAData``.

        This is a convenience bridge used by the human-in-the-loop
        flow: the extracted data is shown to the reviewer and can
        optionally be pre-filled into the ``ConfirmedSLA`` form.

        The penalty clause is assembled from the individual
        financial fields.
        """
        lead_days = self._hours_to_days(data.sla_lead_time_hours)
        penalty_clause = (
            f"Delay penalty: ${data.delay_penalty_rate}/day. "
            f"Missed item penalty: ${data.missed_item_penalty_rate}/unit. "
            f"Quality penalty: {data.quality_penalty_rate * 100}% of order value."
        )
        return SLAContract(
            supplier_name=data.supplier_name,
            material=data.material,
            lead_time_days=lead_days,
            penalty_clause=penalty_clause,
        )

    # ----------------------------------------------------------
    # HITL — persist a ConfirmedSLA
    # ----------------------------------------------------------

    def persist_confirmed_sla(self, confirmed: ConfirmedSLA) -> dict[str, Any]:
        """
        Lift a human-reviewed ``ConfirmedSLA`` and persist it as
        RDF triples in GraphDB.

        The workflow is:

        1. Map ``ConfirmedSLA`` → ``SLAContract`` (the repository's
           native model).
        2. Delegate to ``repository.create_contract_graph()`` which
           builds the SPARQL INSERT and executes it against the
           ``<http://example.org/contracts/>`` named graph.
        3. Return a confirmation dictionary.

        Parameters
        ----------
        confirmed : ConfirmedSLA
            The human-verified and potentially corrected SLA fields
            received from ``POST /api/sandbox/confirm-sla``.

        Returns
        -------
        dict
            Confirmation payload with keys:
            - ``status``: ``"success"``
            - ``supplier``: supplier name
            - ``material``: material name
            - ``graph``: named graph URI
            - ``extraction_id``: link back to the LLM extraction
            - ``triples_inserted``: always 1 (one batch insert)
        """
        contract = SLAContract(
            supplier_name=confirmed.supplier_name,
            material=confirmed.material,
            lead_time_days=confirmed.lead_time_days,
            penalty_clause=confirmed.penalty_clause,
        )

        result = create_contract_graph(contract)

        result["status"] = "success"
        result["extraction_id"] = confirmed.extraction_id
        result["triples_inserted"] = 1

        if confirmed.corrections:
            result["reviewer_notes"] = confirmed.corrections

        logger.info(
            "Persisted ConfirmedSLA(extraction=%s, supplier=%s).",
            confirmed.extraction_id,
            confirmed.supplier_name,
        )
        return result

    # ----------------------------------------------------------
    # Direct SPARQL execution (for batch / non-HITL paths)
    # ----------------------------------------------------------

    def execute_sparql_insert(self, sparql: str) -> dict[str, Any]:
        """
        Execute a raw SPARQL INSERT DATA statement against GraphDB.

        This is the low-level persistence method used by the
        extraction pipeline's injector node when it needs to
        write the LLM output without a human review step
        (e.g., for test / simulation runs).

        Parameters
        ----------
        sparql : str
            A fully-formed SPARQL INSERT DATA query (likely produced
            by ``lift_extracted_data()``).

        Returns
        -------
        dict
            Confirmation dictionary with execution status.
        """
        try:
            graphdb.execute_sparql_update(sparql)
            logger.info("SPARQL INSERT executed successfully against %s.", CONTRACT_GRAPH)
            return {
                "status": "success",
                "graph": CONTRACT_GRAPH,
                "message": "Triples inserted successfully into GraphDB.",
            }
        except Exception as exc:
            logger.error("SPARQL INSERT failed: %s", exc)
            return {
                "status": "error",
                "graph": CONTRACT_GRAPH,
                "message": f"SPARQL INSERT failed: {exc}",
            }


# ----------------------------------------------------------
# Thin service wrapper for non-HITL SLA persistence
# ----------------------------------------------------------


def save_sla_contract(contract: SLAContract) -> dict:
    return create_contract_graph(contract)


# ==============================================================
# 3. MODULE-LEVEL SINGLETON INSTANCE
# ==============================================================
# The lifter is stateless — a single instance can be shared across
# the entire application without thread-safety concerns.

lifter = SemanticLifter()

# Convenience aliases so callers can do:
#   from services.lifting_service import lift_extracted_data
# instead of importing the class directly.

lift_extracted_data = lifter.lift_extracted_data
to_sla_contract = lifter.to_sla_contract
persist_confirmed_sla = lifter.persist_confirmed_sla
execute_sparql_insert = lifter.execute_sparql_insert
