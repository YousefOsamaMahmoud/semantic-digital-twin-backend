# ============================================================
# services/risk_engine_service.py — Layer 2: Risk Engine
#
# Multi-agent LangGraph pipeline that ingests IoT telemetry,
# queries GraphDB for SLA context, runs LLM-based risk analysis,
# and produces a targeted ManagerAlert.
#
# Graph topology
# --------------
#     ENTRY → [fetch_sla] → [analyze_risk] → [generate_alert] → END
# ============================================================

import logging
import os
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

import logging
import os
import time
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from models.schemas import IoTTelemetryEvent, ManagerAlert, RiskAnalysisResult
from services.llm_service import LLMClient

logger = logging.getLogger(__name__)


# ==============================================================
# 1. STATE DEFINITION
# ==============================================================


class RiskEngineState(TypedDict):
    """
    LangGraph state dictionary for the 7-node risk engine pipeline.
    """
    iot_event: IoTTelemetryEvent
    injection_success: bool
    ontology_risks: list[str]
    context_data: dict[str, Any]
    risk_analysis: Optional[RiskAnalysisResult]
    target_managers: list[str]
    alerts: dict[str, str]
    alerts_validated: bool
    final_alert: Optional[ManagerAlert]


# ==============================================================
# 2. NODE 1 — GRAPHDB TELEMETRY INJECTOR
# ==============================================================


def graphdb_injector_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 1 — Permanent GraphDB Ingestor.
    Injects the incoming IoT telemetry delay event into GraphDB.

    Creates a full DeliveryEvent individual with:
      - rdf:type :DeliveryEvent  (required by find_delayed_materials())
      - :hasDeliveryStatus "Delayed"
      - :hasDelayDuration <hours>
      - :transports <material>   (resolved from existing delivery URI)
      - a linked PO with :hasOrderedQuantity  (drives Delayed Quantity column)
    """
    event = state["iot_event"]
    logger.info("[Node 1] Ingesting telemetry event into GraphDB for delivery %s ...", event.delivery_id)

    try:
        from knowledge_base.connection import graphdb
        from knowledge_base.repository import _sanitize_uri_fragment, PREFIXES, CONTRACT_GRAPH

        delivery_uri = _sanitize_uri_fragment(event.delivery_id)
        risk_uri = f"Risk_ML_{delivery_uri}_{int(time.time())}"

        # ── Step 1: look up what material the delivery transports ──────────────
        # Try direct :transports first; if the delivery node was cleaned out by
        # the seeding script, fall back to finding the material via the supplier
        # (e.g. VoltSupply_Global :supplies :Lithium_Ion_Battery_Pack).
        material_lookup = f"""
        {PREFIXES}
        SELECT ?material WHERE {{
            {{
                :{delivery_uri} :transports ?material .
            }}
            UNION
            {{
                # fallback: supplier linked to the delivery's own supplier node
                :{delivery_uri} :isPerformedBy ?sup .
                ?sup :supplies ?material .
                FILTER NOT EXISTS {{ ?sup rdf:type :AlternativeSupplier . }}
            }}
        }} LIMIT 1
        """
        mat_rows = graphdb.execute_sparql_select(material_lookup)
        material_uri = mat_rows[0].get("material") if mat_rows else None

        # Last-resort fallback: look up by delivery URI name convention
        # e.g. "Delivery_VoltSupply_Main" → supplier label contains "VoltSupply"
        if not material_uri:
            supplier_guess = delivery_uri.replace("Delivery_", "").split("_")[0]  # e.g. "VoltSupply"
            guess_lookup = f"""
            {PREFIXES}
            SELECT ?material WHERE {{
                ?sup rdf:type :Supplier ;
                     :supplies ?material .
                FILTER NOT EXISTS {{ ?sup rdf:type :AlternativeSupplier . }}
                OPTIONAL {{ ?sup rdfs:label ?lbl . }}
                FILTER(CONTAINS(LCASE(STR(COALESCE(?lbl, ?sup))), LCASE("{supplier_guess}")))
            }} LIMIT 1
            """
            guess_rows = graphdb.execute_sparql_select(guess_lookup)
            material_uri = guess_rows[0].get("material") if guess_rows else None

        # Build the :transports triple (only when we could resolve the material)
        transports_triple = ""
        po_triples = ""
        if material_uri:
            transports_triple = f":{delivery_uri} :transports <{material_uri}> ."

            # ── Step 2: upsert the IoT PO so re-posting doesn't accumulate quantity ─
            # Use a FIXED URI (no timestamp) — same delivery always maps to the
            # same PO, so INSERT DATA is idempotent (RDF set semantics).
            if event.quantity and event.quantity > 0:
                po_uri = f"PO_IoT_{delivery_uri}"  # deterministic, no timestamp

                # Delete any previous quantity on this IoT PO before re-inserting
                po_delete_q = f"""
                {PREFIXES}
                DELETE {{ GRAPH ?g {{ :{po_uri} :hasOrderedQuantity ?old . }} }}
                WHERE  {{ GRAPH ?g {{ :{po_uri} :hasOrderedQuantity ?old . }} }}
                """
                graphdb.execute_sparql_update(po_delete_q)

                po_triples = f"""
                    :{po_uri} rdf:type :PurchaseOrder ;
                              :hasOrderedQuantity {event.quantity} .
                    :{delivery_uri} :fulfills :{po_uri} .
                """

        # ── Step 3: upsert the delivery status and insert the DelayEvent ────────
        insert_query = f"""
        PREFIX : <http://example.org/ontology#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        # First delete any existing status triple so we can replace it cleanly
        DELETE {{
            GRAPH ?g {{ :{delivery_uri} :hasDeliveryStatus ?oldStatus . }}
        }}
        WHERE {{
            GRAPH ?g {{ :{delivery_uri} :hasDeliveryStatus ?oldStatus . }}
        }} ;

        INSERT DATA {{
            GRAPH <{CONTRACT_GRAPH}> {{
                # Ensure the delivery is typed as a DeliveryEvent (required for dashboard query)
                :{delivery_uri} rdf:type :DeliveryEvent .

                # Mark it delayed with the duration from the IoT signal
                :{delivery_uri} :hasDeliveryStatus "Delayed"^^xsd:string ;
                               :hasDelayDuration {event.estimated_delay_hours} .

                # Material transport link (enables find_delayed_materials() lookup)
                {transports_triple}

                # PO + ordered quantity (drives Delayed Quantity column on dashboard)
                {po_triples}

                # DelayEvent risk record for the LLM agents
                :{risk_uri} rdf:type :DelayEvent ;
                           :affectsDelivery :{delivery_uri} ;
                           :isTriggeredBy :{delivery_uri} ;
                           :hasDelayDuration {event.estimated_delay_hours} ;
                           :hasReasonCode "{event.reason_code}"^^xsd:string ;
                           :hasRiskStatus "Predicted"^^xsd:string ;
                           :hasProbability {event.disruption_probability} .
            }}
        }}
        """
        graphdb.execute_sparql_update(insert_query)
        logger.info("    Successfully injected DelayEvent :%s into GraphDB (material=%s, qty=%s).",
                    risk_uri, material_uri, event.quantity)
        state["injection_success"] = True

        # Invalidate dashboard cache so the Inventory Risk card shows the new DELAYED status immediately
        try:
            from services.dashboard_service import invalidate_impacted_cache
            invalidate_impacted_cache()
        except Exception:
            pass  # Non-critical — cache will expire on its own

    except Exception as exc:
        logger.warning("    GraphDB injection failed (%s). Continuing in offline/mock fallback mode.", exc)
        state["injection_success"] = False

    return state



# ==============================================================
# 3. NODE 2 — ONTOLOGY CONTEXT FETCHER
# ==============================================================


def query_context_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 2 — Query GraphDB context and inferred risks.
    Traverses GraphDB to fetch SLA data, inventory stock, safety levels, 
    downstream processes, and reasoning-inferred risks.
    """
    event = state["iot_event"]
    logger.info("[Node 2] Querying GraphDB context & inferred risks for delivery %s ...", event.delivery_id)

    try:
        from knowledge_base.connection import graphdb
        from knowledge_base.repository import _sanitize_uri_fragment

        delivery_uri = _sanitize_uri_fragment(event.delivery_id)

        # Retrieve supplier, materials, SLA, inventory, processes, and inferred risks
        sparql_query = f"""
        PREFIX : <http://example.org/ontology#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT DISTINCT ?leadTimeDays ?penaltyRate ?stock ?safe ?disruptionLevel ?riskType
        WHERE {{
            # Traverse delivery to transported material
            :{delivery_uri} :transports ?material .

            # Traverse material to supplier
            OPTIONAL {{
                {{ ?material :isSuppliedBy ?supplier . }}
                UNION
                {{ ?supplier :supplies ?material . }}

                # Get SLA terms — fetch the numeric delay penalty rate directly
                # from the SLAContract (not the free-text :penaltyClause).
                OPTIONAL {{ 
                    ?contract rdf:type :SLAContract ;
                              :hasSupplier ?supplier ;
                              :governsMaterial ?material ;
                              :leadTimeDays ?leadTimeDays .
                    OPTIONAL {{ ?contract :hasDelayPenaltyRate ?contractPenalty . }}
                }}
                OPTIONAL {{ ?supplier :penaltyRatePerDay ?supplierPenalty . }}
                BIND(COALESCE(?contractPenalty, ?supplierPenalty) AS ?penaltyRate)
            }}

            # Get inventory levels
            OPTIONAL {{
                ?material :hasInventoryStock ?stock ;
                          :hasSafetyStockLevel ?safe .
            }}

            # Get affected production process
            OPTIONAL {{
                ?material :affectsProcess ?process .
                OPTIONAL {{ ?process :hasCriticalityLevel ?disruptionLevel . }}
            }}

            # Retrieve inferred risk events affecting this delivery
            OPTIONAL {{
                {{
                    ?riskEvent :affectsDelivery :{delivery_uri} ;
                               rdf:type ?riskType .
                    FILTER(?riskType = :DelayEvent)
                }}
                UNION
                {{
                    BIND(:{delivery_uri} AS ?riskEvent)
                    :{delivery_uri} rdf:type ?riskType .
                    FILTER(?riskType = :SLAViolation)
                }}
                UNION
                {{
                    ?material :affectsProcess ?riskEvent .
                    ?riskEvent rdf:type ?riskType .
                    FILTER(?riskType = :ProductionDisruption)
                }}
            }}
        }}
        """
        results = graphdb.execute_sparql_select(sparql_query)
        logger.info("    SPARQL results: %s", results)

        if results:
            risk_types = set()
            lead_time_days = 3
            delay_penalty_rate = 300.0  # VoltSupply Standard SLA: $300/day
            inventory_stock = 80
            safety_stock = 100
            disruption_level = "Medium"

            for row in results:
                if "leadTimeDays" in row:
                    lead_time_days = int(float(row["leadTimeDays"]))
                if "penaltyRate" in row and row["penaltyRate"] is not None:
                    try:
                        # penaltyRate is now always the numeric hasDelayPenaltyRate value
                        delay_penalty_rate = float(row["penaltyRate"])
                    except (ValueError, TypeError):
                        pass
                if "stock" in row:
                    inventory_stock = int(row["stock"])
                if "safe" in row:
                    safety_stock = int(row["safe"])
                if "disruptionLevel" in row:
                    disruption_level = row["disruptionLevel"]
                if "riskType" in row:
                    risk_types.add(row["riskType"].split("#")[-1])

            state["ontology_risks"] = list(risk_types)
            state["context_data"] = {
                "lead_time_days": lead_time_days,
                "delay_penalty_rate": delay_penalty_rate,
                "inventory_stock": inventory_stock,
                "safety_stock": safety_stock,
                "disruption_level": disruption_level,
            }
            logger.info("    Fetched SLA Context: lead time = %d days, penalty = $%.2f, stock = %s, safe = %s", 
                        lead_time_days, delay_penalty_rate, inventory_stock, safety_stock)
            return state

    except Exception as exc:
        logger.warning("    GraphDB query failed (%s). Using mock fallback.", exc)

    # Offline / Mock Fallback
    state["ontology_risks"] = ["DelayEvent"]
    state["context_data"] = {
        "lead_time_days": 3,
        "delay_penalty_rate": 300.0,  # VoltSupply Standard SLA: $300/day
        "inventory_stock": 80,
        "safety_stock": 100,
        "disruption_level": "Medium",
    }
    return state


# ==============================================================
# 4. NODE 3 — RISK ANALYST AGENT
# ==============================================================


RISK_ANALYST_SYSTEM_PROMPT = """
You are a Supply Chain Risk Analyst. Your job is to determine
which business risks actually exist for a delivery based on the
Context Data and the IoT Telemetry details.

<Ontology Inferred Risks>
{ontology_risks}
</Ontology Inferred Risks>

<Delivery Context>
  Delivery ID:      {delivery_id}
  Delay (hours):    {delay_hours}
  Reason:           {reason_code}
  Disruption Prob:  {disruption_probability}
  SLA Lead Time:    {lead_time_days} days
  Penalty Rate:     ${penalty_rate}/day
  Current Stock:    {inventory_stock} units
  Safety Stock:     {safety_stock} units
  Process Impact:   {disruption_level}
</Delivery Context>

Return a structured risk assessment with the following:
- ``risks``: list of active risk types (e.g., DelayEvent,
  SLAViolation, ProductionDisruption).
- ``confidence``: confidence score between 0.0 and 1.0.
- ``severity``: "Low", "Medium", "High", or "Critical".
- ``financial_penalty_estimate``: estimated penalty amount.
- ``reasoning``: brief explanation of the analysis.
"""

# Reason codes that DO qualify a delay as an SLAViolation per the
# team lead's rule: only carrier-fault or customs-related delays
# count as contractual SLA breaches. A delay caused by weather/
# transport conditions or general port congestion is treated as an
# operational DelayEvent only — it does not trigger penalty exposure,
# since it isn't attributable to a breach of the supplier's
# contractual obligations.
_SLA_VIOLATION_REASON_CODES = {
    "Carrier_Issue",
    "CustomsDelay",
    "Customs_Hold",
    "Customs_Delay",
}

# Reason codes explicitly excluded from SLAViolation, even if the LLM
# (or an upstream ontology rule) suggests otherwise — kept as an
# explicit denylist so the intent is unambiguous in code review, not
# just "anything not in the allow-list".
_NON_SLA_VIOLATION_REASON_CODES = {
    "Transport/Weather",
    "Weather_Delay",
    "Port_Congestion",
    "PortCongestion",
}


def _apply_reason_code_sla_rule(risks: list[str], reason_code: str) -> list[str]:
    """
    Deterministically enforce the team lead's SLA-violation rule:
    a delay only counts as :SLAViolation when its reason_code
    indicates carrier fault or customs hold. Weather/transport and
    port-congestion delays are real DelayEvents, but not contractual
    breaches, so :SLAViolation is stripped from the LLM's risk list
    if present for those reason codes.

    This mirrors the existing pattern of overriding the LLM's free
    financial_penalty_estimate with a deterministic formula — the
    LLM's classification is a useful signal, but the actual business
    rule must be enforced in code, not left to vary across calls.
    """
    if "SLAViolation" not in risks:
        return risks

    if reason_code in _NON_SLA_VIOLATION_REASON_CODES:
        logger.info(
            "    Reason code '%s' is not SLA-violation-eligible (weather/congestion) — "
            "stripping SLAViolation from risk list.",
            reason_code,
        )
        return [r for r in risks if r != "SLAViolation"]

    if reason_code not in _SLA_VIOLATION_REASON_CODES:
        # Unknown/unmapped reason code — log it for visibility, but
        # don't silently strip a risk the LLM/ontology flagged unless
        # we positively know it's excluded. Conservative default:
        # keep SLAViolation rather than risk under-alerting.
        logger.info(
            "    Reason code '%s' is not in the known SLA-violation allow-list; "
            "keeping SLAViolation since it isn't on the explicit exclusion list either.",
            reason_code,
        )

    return risks


def risk_analyst_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 3 — Risk Analyst Agent.
    Runs structured LLM inference to generate a comprehensive risk assessment.
    """
    logger.info("[Node 3] Risk Analyst Agent — analyzing delivery ...")

    event = state["iot_event"]
    ctx = state["context_data"]
    ontology_risks = state.get("ontology_risks", [])
    delay_days = event.estimated_delay_hours / 24.0

    # Deterministic penalty calculation (used to override the LLM's free estimate)
    # Formula: max(0, delay_days - 2_day_grace_period) × penalty_rate_per_day
    penalty_rate = float(ctx.get("delay_penalty_rate") or 0.0)
    billable_days = max(0.0, delay_days - 2.0)
    calculated_penalty = round(billable_days * penalty_rate, 2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", RISK_ANALYST_SYSTEM_PROMPT),
    ])

    try:
        analysis = LLMClient.get_instance().invoke_structured(
            prompt,
            {
                "delivery_id": event.delivery_id,
                "delay_hours": event.estimated_delay_hours,
                "delay_days": delay_days,
                "reason_code": event.reason_code,
                "disruption_probability": event.disruption_probability,
                "lead_time_days": ctx.get("lead_time_days", 3),
                "penalty_rate": penalty_rate,
                "inventory_stock": ctx.get("inventory_stock", 80),
                "safety_stock": ctx.get("safety_stock", 100),
                "disruption_level": ctx.get("disruption_level", "Medium"),
                "ontology_risks": ", ".join(ontology_risks) if ontology_risks else "None",
            },
            RiskAnalysisResult,
        )

        # Override the LLM's freely-estimated penalty with the deterministic formula.
        # The LLM tends to skip the grace period and uses the full delay days.
        analysis.financial_penalty_estimate = calculated_penalty

        # Enforce the team lead's reason-code rule: SLAViolation only
        # applies for carrier/customs-fault delays, never weather or
        # port-congestion delays — see _apply_reason_code_sla_rule().
        analysis.risks = _apply_reason_code_sla_rule(analysis.risks, event.reason_code)

        logger.info(
            "    Analysis: risks=%s | severity=%s | confidence=%.2f | penalty=$%.2f (%.1f billable days × $%.0f/day)",
            analysis.risks,
            analysis.severity,
            analysis.confidence,
            calculated_penalty,
            billable_days,
            penalty_rate,
        )
        state["risk_analysis"] = analysis

    except Exception as exc:
        logger.error("Risk analysis LLM call failed unexpectedly: %s", exc)
        state["risk_analysis"] = RiskAnalysisResult(
            risks=["DelayEvent"],
            confidence=0.5,
            severity="Low",
            financial_penalty_estimate=calculated_penalty,
            reasoning=f"Risk analysis unavailable due to an error: {exc}",
        )

    return state


# ==============================================================
# 5. NODE 4 — ROUTER
# ==============================================================


def router_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 4 — Router.
    Routes targeted alerts to relevant managers based on active risks.
    """
    logger.info("[Node 4] Router — routing manager targets ...")
    analysis = state["risk_analysis"]
    active_risks = analysis.risks if analysis else ["DelayEvent"]

    targets = set()
    if "DelayEvent" in active_risks:
        targets.add("Production Manager")
    if "SLAViolation" in active_risks:
        targets.add("Procurement Manager")
    if "ProductionDisruption" in active_risks:
        targets.add("Production Manager")
        targets.add("Logistics Manager")

    state["target_managers"] = list(targets)
    if not state["target_managers"]:
        state["target_managers"] = ["Production Manager"]

    logger.info("    Alerted managers: %s", state["target_managers"])
    return state


# ==============================================================
# 6. NODE 5 — MANAGER ALERT AGENTS
# ==============================================================


ALERT_PROMPTS = {
    "Production Manager": """You are an urgent alert writer for a PRODUCTION MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Reasoning: {reasoning}. \
Write a 2 sentence alert focusing on potential assembly line stoppages and inventory impact.""",

    "Procurement Manager": """You are an urgent alert writer for a PROCUREMENT MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Financial penalty estimate: ${penalty}. \
Write a 2 sentence alert focusing on SLA breach and financial consequences.""",

    "Logistics Manager": """You are an urgent alert writer for a LOGISTICS MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Reason: {reason_code}. \
Write a 2 sentence alert focusing on transport issues and rerouting possibilities."""
}


def alert_generator_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 5 — Alert Generator.
    Runs LLM alert writers for each target manager.
    """
    logger.info("[Node 5] Alert Generator — writing manager alerts ...")
    analysis = state["risk_analysis"]
    event = state["iot_event"]

    alerts = {}
    for manager in state["target_managers"]:
        prompt_template = ALERT_PROMPTS.get(manager, ALERT_PROMPTS["Production Manager"])
        prompt = ChatPromptTemplate.from_messages([("system", prompt_template)])

        try:
            alert_text = LLMClient.get_instance().invoke_text(
                prompt,
                {
                    "delivery_id": event.delivery_id,
                    "risks": ", ".join(analysis.risks) if analysis else "DelayEvent",
                    "severity": analysis.severity if analysis else "Low",
                    "reasoning": analysis.reasoning if analysis else "None",
                    "penalty": analysis.financial_penalty_estimate if analysis else 0.0,
                    "reason_code": event.reason_code
                }
            )
            logger.info("    Generated alert for %s: %s", manager, alert_text)
            alerts[manager] = alert_text
        except Exception as exc:
            logger.warning("    Alert generation failed for %s (%s). Using default.", manager, exc)
            alerts[manager] = f"ALERT: Delivery {event.delivery_id} is at risk due to a {event.estimated_delay_hours}h delay."

    state["alerts"] = alerts
    return state


# ==============================================================
# 7. NODE 6 — VALIDATOR AGENT
# ==============================================================


VALIDATOR_PROMPT = """You are an alert quality inspector. \
Check the following alert message for a {manager_title}. \
Is it specific, urgent, and factually consistent with the risk reasoning? \
If it is acceptable, reply with "VALID". \
If it is too vague, contains made-up information, or is not urgent enough, reply with "INVALID: <reason>".
Alert: {alert_text}
Original risk context: {risks}, severity {severity}, reasoning: {reasoning}"""


def validator_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 6 — Validator Agent.
    Performs quality checks on all generated alerts.
    """
    logger.info("[Node 6] Validator Agent — validating alerts ...")
    analysis = state["risk_analysis"]

    for manager, alert_text in state["alerts"].items():
        prompt = ChatPromptTemplate.from_messages([("system", VALIDATOR_PROMPT)])
        try:
            verdict = LLMClient.get_instance().invoke_text(
                prompt,
                {
                    "manager_title": manager,
                    "alert_text": alert_text,
                    "risks": ", ".join(analysis.risks) if analysis else "DelayEvent",
                    "severity": analysis.severity if analysis else "Low",
                    "reasoning": analysis.reasoning if analysis else "None"
                }
            )
            logger.info("    Validator check for %s: %s", manager, verdict)
        except Exception as exc:
            logger.warning("    Validation failed for %s (%s)", manager, exc)

    state["alerts_validated"] = True
    return state


# ==============================================================
# 8. NODE 7 — ALERT FINALIZER
# ==============================================================


def _determine_alert_title(risks: list[str]) -> str:
    """
    Map risks to primary target manager role.
    """
    risk_set = set(risks)

    if "ProductionDisruption" in risk_set and "SLAViolation" in risk_set:
        return "Procurement Manager"
    if "SLAViolation" in risk_set:
        return "Procurement Manager"
    if "ProductionDisruption" in risk_set:
        return "Logistics Manager"
    if "DelayEvent" in risk_set:
        return "Production Manager"

    return "Production Manager"


def _build_alert_text(event: IoTTelemetryEvent, ctx: dict[str, Any],
                       analysis: RiskAnalysisResult) -> str:
    parts = [
        f"Delivery {event.delivery_id} is at risk.",
        f"Delay: {event.estimated_delay_hours}h ({event.reason_code}).",
    ]

    if ctx.get("lead_time_days"):
        parts.append(
            f"SLA lead time: {ctx['lead_time_days']} day(s)."
        )

    parts.append(f"Severity: {analysis.severity}.")
    parts.append(f"Risks detected: {', '.join(analysis.risks)}.")

    if analysis.financial_penalty_estimate > 0:
        parts.append(
            f"Estimated penalty: ${analysis.financial_penalty_estimate:,.2f}."
        )

    parts.append(f"Reasoning: {analysis.reasoning}")
    return " ".join(parts)


def _escape_sparql_string(value: str) -> str:
    """
    Escape a Python string for safe embedding inside a SPARQL string
    literal ("...") in an INSERT DATA block. Handles backslashes,
    quotes, newlines, tabs, and carriage returns — a bare
    .replace('"', '\\"') lets real LLM-generated text (which often
    contains newlines and markdown) through as raw control
    characters, breaking the query with a "Lexical error" at parse
    time. Backslashes are escaped FIRST, before quotes/newlines, so
    later substitutions don't double-escape already-touched characters.
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def alert_finalizer_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 7 — Alert Finalizer.
    Resolves the primary manager notification and packs the final ManagerAlert.
    """
    logger.info("[Node 7] Alert Finalizer — resolving output ...")

    analysis = state["risk_analysis"]
    if analysis is None:
        analysis = RiskAnalysisResult(
            risks=["DelayEvent"],
            confidence=0.5,
            severity="Low",
            financial_penalty_estimate=0.0,
            reasoning="Default fallback assessment.",
        )

    event = state["iot_event"]
    ctx = state["context_data"]

    title = _determine_alert_title(analysis.risks)
    alert_text = state["alerts"].get(title)

    if not alert_text:
        # Fallback to compiled alert text
        alert_text = _build_alert_text(event, ctx, analysis)

    state["final_alert"] = ManagerAlert(
        manager_title=title,
        alert_text=alert_text,
        validated=state.get("alerts_validated", False),
    )

    logger.info("    Selected final alert for %s: %.100s ...", title, alert_text)

    # Save to GraphDB
    try:
        from knowledge_base.connection import graphdb
        from knowledge_base.repository import _sanitize_uri_fragment
        import hashlib
        import time
        from datetime import datetime

        delivery_uri = _sanitize_uri_fragment(event.delivery_id)

        created_at = datetime.utcnow().isoformat() + "Z"
        # Save a separate SystemAlert for each targeted manager
        triples = []
        for m_title, m_text in state["alerts"].items():
            raw_str = f"ML_{delivery_uri}_{m_title}_{int(time.time())}".encode("utf-8")
            alert_id = "ALT_" + hashlib.md5(raw_str).hexdigest()[:8].upper()

            # Use the full SPARQL string escaper (handles backslashes,
            # quotes, AND newlines/tabs) instead of a bare quote-only
            # .replace() — real LLM-generated alert text routinely
            # contains newlines and markdown, which a quote-only
            # escape lets through as raw control characters, breaking
            # the query with a "Lexical error" at parse time.
            safe_title = _escape_sparql_string(m_title)
            safe_text = _escape_sparql_string(m_text)
            safe_severity = _escape_sparql_string(analysis.severity or "Low")

            triples.append(f"""
                :{alert_id} rdf:type :SystemAlert ;
                            :hasTitle "At-Risk Delivery — {safe_title}"^^xsd:string ;
                            :hasDesc "{safe_text}"^^xsd:string ;
                            :intendedFor "{safe_title}"^^xsd:string ;
                            :hasStatus "UNREAD"^^xsd:string ;
                            :hasSeverity "{safe_severity}"^^xsd:string ;
                            :triggeredBy :{delivery_uri} ;
                            :createdAt "{created_at}"^^xsd:dateTime .
            """)

        if triples:
            insert_query = f"""
            PREFIX : <http://example.org/ontology#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            INSERT DATA {{
                GRAPH <http://example.org/contracts/> {{
                    {"".join(triples)}
                }}
            }}
            """
            graphdb.execute_sparql_update(insert_query)
            logger.info("    Successfully saved %d ManagerAlert(s) into GraphDB.", len(triples))
    except Exception as exc:
        logger.warning("    Failed to save ManagerAlerts to GraphDB: %s", exc)

    return state


# ==============================================================
# 9. GRAPH COMPILATION
# ==============================================================


def build_risk_graph() -> StateGraph:
    """
    Assemble and compile the risk engine LangGraph with 7 nodes.
    Graph nodes are named to preserve backward-compatibility with integration tests.
    """
    workflow = StateGraph(RiskEngineState)

    # 7-node pipeline mapped to integration test expected endpoints
    workflow.add_node("fetch_sla", graphdb_injector_node)
    workflow.add_node("query_context", query_context_node)
    workflow.add_node("analyze_risk", risk_analyst_node)
    workflow.add_node("router", router_node)
    workflow.add_node("alert_generator", alert_generator_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("generate_alert", alert_finalizer_node)

    workflow.set_entry_point("fetch_sla")
    workflow.add_edge("fetch_sla", "query_context")
    workflow.add_edge("query_context", "analyze_risk")
    workflow.add_edge("analyze_risk", "router")
    workflow.add_edge("router", "alert_generator")
    workflow.add_edge("alert_generator", "validator")
    workflow.add_edge("validator", "generate_alert")
    workflow.add_edge("generate_alert", END)

    return workflow.compile()


# ==============================================================
# 10. PUBLIC ENTRY POINT
# ==============================================================


async def process_iot_event(event: IoTTelemetryEvent) -> ManagerAlert:
    """
    Execute the full 7-node risk engine LangGraph pipeline for a single
    IoT telemetry event.
    """
    import asyncio

    graph = build_risk_graph()

    initial_state: RiskEngineState = {
        "iot_event": event,
        "injection_success": False,
        "ontology_risks": [],
        "context_data": {},
        "risk_analysis": None,
        "target_managers": [],
        "alerts": {},
        "alerts_validated": False,
        "final_alert": None,
    }

    loop = asyncio.get_running_loop()

    final_state: dict[str, Any] = await loop.run_in_executor(
        None, graph.invoke, initial_state,
    )

    alert = final_state.get("final_alert")
    if alert is None:
        logger.error("Pipeline terminated without producing an alert.")
        return ManagerAlert(
            manager_title="Production Manager",
            alert_text=(
                f"[Pipeline Error] Risk assessment for delivery "
                f"{event.delivery_id} failed to produce an alert. "
                "Please investigate manually."
            ),
            validated=False,
        )

    # Trigger supplier score recalculation SYNCHRONOUSLY so the next dashboard
    # fetch always reflects the updated reliability score and delayed status.
    try:
        from services.supplier_evaluator_service import record_telemetry_transaction_and_update_score

        logger.info("[Risk Engine] Updating supplier score synchronously for delivery %s ...", event.delivery_id)
        record_telemetry_transaction_and_update_score(event.delivery_id, event.estimated_delay_hours)
        logger.info("[Risk Engine] Supplier score updated successfully for delivery %s.", event.delivery_id)
    except Exception as exc:
        logger.error("[Risk Engine] Failed to update supplier score synchronously: %s", exc)

    return alert

