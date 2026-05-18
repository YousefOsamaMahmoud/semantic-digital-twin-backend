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

from models.schemas import IoTTelemetryEvent, ManagerAlert, RiskAnalysisResult
from services.llm_service import LLMClient

logger = logging.getLogger(__name__)


# ==============================================================
# 1. STATE DEFINITION
# ==============================================================


class RiskEngineState(TypedDict):
    """
    LangGraph state dictionary for the risk engine pipeline.

    Keys
    ----
    iot_event : IoTTelemetryEvent
        The incoming IoT telemetry that triggered the pipeline.
    sla_data : dict
        SLA context fetched from GraphDB (or mocked in dev mode).
        Expected keys: lead_time_days, delay_penalty_rate.
    risk_analysis : RiskAnalysisResult | None
        Structured LLM risk assessment (None before analysis runs).
    final_alert : ManagerAlert | None
        The formatted alert produced by the pipeline (None before
        generation runs).
    """

    iot_event: IoTTelemetryEvent
    sla_data: dict[str, Any]
    risk_analysis: Optional[RiskAnalysisResult]
    final_alert: Optional[ManagerAlert]


# ==============================================================
# 2. NODE 1 — SLA CONTEXT FETCHER
# ==============================================================


def fetch_sla_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 1 — Fetch SLA context for the delivery referenced by the
    IoT telemetry event.

    **Production behaviour** (when GraphDB is reachable):

        Run a SPARQL SELECT against the ``contracts/`` named graph
        to retrieve ``lead_time_days`` and ``delay_penalty_rate``
        for the supplier associated with ``iot_event.delivery_id``.

    **Current behaviour** (testing / development):

        Returns a hard-coded mock SLA dictionary so the pipeline
        can be tested without a running GraphDB instance.
    """
    logger.info("[Node 1] Fetching SLA context for delivery %s …",
                state["iot_event"].delivery_id)

    # ── Attempt real GraphDB query ──────────────────────────
    try:
        from knowledge_base.connection import graphdb

        sparql_query = f"""
        PREFIX : <http://example.org/ontology#>
        SELECT ?leadTimeDays ?penaltyRate WHERE {{
            ?delivery rdf:type :DeliveryEvent ;
                      :hasDeliveryStatus "Delayed" .
            OPTIONAL {{ ?delivery :leadTimeDays ?leadTimeDays . }}
            OPTIONAL {{ ?delivery :penaltyClause ?penaltyRate . }}
        }}
        LIMIT 1
        """
        results = graphdb.execute_sparql_select(sparql_query)
        if results:
            row = results[0]
            sla_data = {
                "lead_time_days": int(row.get("leadTimeDays", 3)),
                "delay_penalty_rate": float(
                    row.get("penaltyRate", "500").replace("$", "").split("/")[0]
                ),
            }
            logger.info("    SLA context fetched from GraphDB: %s", sla_data)
            state["sla_data"] = sla_data
            return state
    except Exception as exc:
        logger.warning("GraphDB query failed (%s). Falling back to mock SLA.", exc)

    # ── Fallback mock for development / testing ─────────────
    mock_sla: dict[str, Any] = {
        "lead_time_days": 3,
        "delay_penalty_rate": 500.0,
        "delivery_id": state["iot_event"].delivery_id,
    }
    logger.info("    Using mock SLA data: %s", mock_sla)
    state["sla_data"] = mock_sla
    return state


# ==============================================================
# 3. NODE 2 — RISK ANALYST AGENT
# ==============================================================


RISK_ANALYST_SYSTEM_PROMPT = """
You are a Supply Chain Risk Analyst. Your job is to determine
which business risks actually exist for a delivery based on the
Context Data and the IoT Telemetry details.

<Delivery Context>
  Delivery ID:      {delivery_id}
  Delay (hours):    {delay_hours}
  Reason:           {reason_code}
  Disruption Prob:  {disruption_probability}
  SLA Lead Time:    {lead_time_days} days
  Penalty Rate:     ${penalty_rate}/day
</Delivery Context>

Return a structured risk assessment with the following:
- ``risks``: list of active risk types (e.g., DelayEvent,
  SLAViolation, ProductionDisruption).
- ``confidence``: confidence score between 0.0 and 1.0.
- ``severity``: "Low", "Medium", "High", or "Critical".
- ``financial_penalty_estimate``: estimated penalty amount.
- ``reasoning``: brief explanation of the analysis.
"""


def analyze_risk_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 2 — Risk Analyst Agent.

    Calls the LLM with ``.with_structured_output(RiskAnalysisResult)``
    to produce a structured risk assessment from the IoT telemetry
    and the fetched SLA context.

    **Fallback behaviour**

    When the LLM is unreachable (no API key, quota exhausted) the
    ``invoke_structured`` call returns a deterministic
    ``RiskAnalysisResult`` with conservative defaults (severity
    "Low", confidence 0.5, risks ["DelayEvent"]).  This guarantees
    the pipeline never crashes and still produces a valid
    ``ManagerAlert`` for integration testing.
    """
    logger.info("[Node 2] Risk Analyst Agent — analysing delivery …")

    event = state["iot_event"]
    sla = state["sla_data"]
    delay_days = event.estimated_delay_hours / 24.0

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
                "lead_time_days": sla.get("lead_time_days", 3),
                "penalty_rate": sla.get("delay_penalty_rate", 500.0),
            },
            RiskAnalysisResult,
        )

        logger.info(
            "    Analysis: risks=%s | severity=%s | confidence=%.2f",
            analysis.risks,
            analysis.severity,
            analysis.confidence,
        )
        state["risk_analysis"] = analysis

    except Exception as exc:
        logger.error("Risk analysis LLM call failed unexpectedly: %s", exc)
        # Last-resort safety net: build a minimal fallback in-line.
        state["risk_analysis"] = RiskAnalysisResult(
            risks=["DelayEvent"],
            confidence=0.0,
            severity="Low",
            financial_penalty_estimate=0.0,
            reasoning=f"Risk analysis unavailable due to an error: {exc}",
        )

    return state


# ==============================================================
# 4. NODE 3 — ALERT GENERATOR
# ==============================================================


def _determine_alert_title(risks: list[str]) -> str:
    """
    Map the set of active risks to the most relevant manager role.

    Logic (mirrors the original ``impact_mitigation_agents_v3.py``
    router):

    - ``ProductionDisruption`` or ``DelayEvent`` → Production Manager
    - ``SLAViolation`` → Procurement Manager
    - ``ProductionDisruption`` also → Logistics Manager
    - Fallback (empty or unrecognised) → Production Manager
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


def _build_alert_text(event: IoTTelemetryEvent, sla: dict[str, Any],
                       analysis: RiskAnalysisResult) -> str:
    """
    Assemble a concise, informative alert message from the pipeline
    data.
    """
    parts = [
        f"Delivery {event.delivery_id} is at risk.",
        f"Delay: {event.estimated_delay_hours}h ({event.reason_code}).",
    ]

    if sla.get("lead_time_days"):
        parts.append(
            f"SLA lead time: {sla['lead_time_days']} day(s)."
        )

    parts.append(f"Severity: {analysis.severity}.")
    parts.append(f"Risks detected: {', '.join(analysis.risks)}.")

    if analysis.financial_penalty_estimate > 0:
        parts.append(
            f"Estimated penalty: ${analysis.financial_penalty_estimate:,.2f}."
        )

    parts.append(f"Reasoning: {analysis.reasoning}")
    return " ".join(parts)


def generate_alert_node(state: RiskEngineState) -> RiskEngineState:
    """
    Node 3 — Alert Generator.

    Takes the validated ``RiskAnalysisResult`` and formats it into
    a ``ManagerAlert`` targeted at the most relevant manager role.
    """
    logger.info("[Node 3] Alert Generator — formatting alert …")

    analysis = state["risk_analysis"]

    # Safety guard — if the previous node failed to produce an
    # analysis, build an ultra-conservative one so the pipeline
    # still terminates gracefully.
    if analysis is None:
        logger.warning("    No risk analysis available — building empty alert.")
        analysis = RiskAnalysisResult(
            risks=["Unknown"],
            confidence=0.0,
            severity="Low",
            financial_penalty_estimate=0.0,
            reasoning="No risk analysis was produced by the pipeline.",
        )

    event = state["iot_event"]
    sla = state["sla_data"]

    title = _determine_alert_title(analysis.risks)
    text = _build_alert_text(event, sla, analysis)

    alert = ManagerAlert(
        manager_title=title,
        alert_text=text,
        validated=False,
    )

    logger.info("    Alert for %s: %.120s …", title, text)
    state["final_alert"] = alert
    return state


# ==============================================================
# 5. GRAPH COMPILATION
# ==============================================================


def build_risk_graph() -> StateGraph:
    """
    Assemble and compile the risk engine LangGraph.

    Topology
    --------
        ENTRY → [fetch_sla] → [analyze_risk] → [generate_alert] → END
    """
    workflow = StateGraph(RiskEngineState)

    workflow.add_node("fetch_sla", fetch_sla_node)
    workflow.add_node("analyze_risk", analyze_risk_node)
    workflow.add_node("generate_alert", generate_alert_node)

    workflow.set_entry_point("fetch_sla")
    workflow.add_edge("fetch_sla", "analyze_risk")
    workflow.add_edge("analyze_risk", "generate_alert")
    workflow.add_edge("generate_alert", END)

    return workflow.compile()


# ==============================================================
# 6. PUBLIC ENTRY POINT
# ==============================================================


async def process_iot_event(event: IoTTelemetryEvent) -> ManagerAlert:
    """
    Execute the full risk engine LangGraph pipeline for a single
    IoT telemetry event.

    This is the single public API for the API layer
    (``api/dashboard.py`` → ``POST /api/risk/assess`` or similar).

    The function is ``async`` so it can be called directly from a
    FastAPI ``async def`` endpoint without blocking the event loop.
    The underlying LangGraph ``invoke`` is dispatched to a thread
    pool via ``asyncio.get_running_loop().run_in_executor()``.

    Parameters
    ----------
    event : IoTTelemetryEvent
        The validated IoT telemetry payload received from the
        frontend, an MQTT bridge, or an ML prediction service.

    Returns
    -------
    ManagerAlert
        The final alert produced by the pipeline, targeted at the
        most relevant manager role and containing a human-readable
        risk assessment message.
    """
    import asyncio

    graph = build_risk_graph()

    initial_state: RiskEngineState = {
        "iot_event": event,
        "sla_data": {},
        "risk_analysis": None,
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

    return alert
