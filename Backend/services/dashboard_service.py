# ============================================================
# services/dashboard_service.py — Layer 2: Dashboard Logic
#
# Thin service layer that wraps knowledge_base repository
# functions and SPARQL query building for the dashboard API.
# API endpoints MUST NOT import knowledge_base directly.
# ============================================================

import logging

from knowledge_base.connection import graphdb
from knowledge_base.repository import (
    PREFIXES,
    _sanitize_uri_fragment,
    find_impacted_products_by_supplier_delay,
)

logger = logging.getLogger(__name__)


def get_risk_scores() -> list[dict]:
    results = find_impacted_products_by_supplier_delay()
    risk_scores = []
    for row in results:
        risk_scores.append({
            "product": row.get("productLabel", "Unknown"),
            "supplier": row.get("supplierLabel", "Unknown"),
            "material": row.get("materialLabel", "Unknown"),
            "status": (
                "RED" if row.get("riskStatus", "").lower() == "true"
                else "GREEN"
            ),
        })
    return risk_scores


def get_compliance_alerts() -> list[dict]:
    query = f"""
    {PREFIXES}
    SELECT ?supplier ?material ?leadTimeDays ?penalty
    WHERE {{
        ?supplier rdf:type :Supplier ;
                  :supplies ?material ;
                  :leadTimeDays ?leadTimeDays .
        ?material rdf:type :RawMaterial .
        OPTIONAL {{ ?supplier :penaltyClause ?penalty . }}
    }}
    """
    return graphdb.execute_sparql_select(query)


def get_impacted_products() -> list[dict]:
    return find_impacted_products_by_supplier_delay()


def get_fallback_options(material_id: str) -> list[dict]:
    safe_material = _sanitize_uri_fragment(material_id)
    query = f"""
    {PREFIXES}
    SELECT DISTINCT ?supplier ?supplierName ?reliabilityScore
    WHERE {{
        ?supplier rdf:type :Supplier ;
                  rdfs:label ?supplierName ;
                  :supplies :{safe_material} .
        OPTIONAL {{ ?supplier :hasReliabilityScore ?reliabilityScore . }}
    }}
    ORDER BY DESC(?reliabilityScore)
    """
    return graphdb.execute_sparql_select(query)
