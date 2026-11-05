# ============================================================
# api/dashboard.py — Layer 1: Dashboard API Router
#
# Dashboard endpoints for NL chat, risk scores, compliance
# alerts, and fallback supplier options.
# ============================================================

import logging

from fastapi import APIRouter, HTTPException

from services.dashboard_service import (
    get_compliance_alerts,
    get_fallback_options,
    get_risk_scores,
    get_kpis,
    get_alerts,
    assign_fallback_supplier,
    get_assembly_lines,
    get_assembly_line_for_material,
    assign_material_to_process,
    update_alert_status,
    create_fallback_request_alert,
    get_active_sla,
)
from services.chat_service import run_chat_pipeline_async
from pydantic import BaseModel

class FallbackAssignmentRequest(BaseModel):
    material: str
    supplierName: str
    assignmentType: str

class AlertStatusUpdate(BaseModel):
    alert_id: str

class FallbackRequest(BaseModel):
    material: str
    risk_percent: int

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get("/risk-scores")
async def handle_risk_scores():
    try:
        risk_scores = get_risk_scores()
        return {
            "status": "success",
            "count": len(risk_scores),
            "risk_scores": risk_scores,
        }
    except Exception as exc:
        logger.error("Failed to fetch risk scores: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/compliance-alerts")
async def handle_compliance_alerts():
    try:
        results = get_compliance_alerts()
        return {"status": "success", "count": len(results), "alerts": results}
    except Exception as exc:
        logger.error("Failed to fetch compliance alerts: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/fallback-options/{material_id}")
async def handle_fallback_options(material_id: str):
    try:
        results = get_fallback_options(material_id)
        return {
            "status": "success",
            "count": len(results),
            "material": material_id,
            "suppliers": results,
        }
    except Exception as exc:
        logger.error("Failed to fetch fallback options: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/active-sla")
async def handle_active_sla(supplier: str, material: str):
    try:
        result = get_active_sla(supplier, material)
        return {
            "status": "success",
            "exists": result is not None,
            "sla": result
        }
    except Exception as exc:
        logger.error("Failed to fetch active SLA: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/assign-fallback")
async def handle_assign_fallback(request: FallbackAssignmentRequest):
    try:
        result = assign_fallback_supplier(request.material, request.supplierName, request.assignmentType)
        return result
    except Exception as exc:
        logger.error("Failed to assign fallback supplier: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/kpis")
async def handle_kpis(role: str = None):
    try:
        kpis = get_kpis(role=role)
        return {
            "status": "success",
            "kpis": kpis,
        }
    except Exception as exc:
        logger.error("Failed to fetch KPIs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/alerts")
async def handle_alerts():
    try:
        alerts = get_alerts()
        return {
            "status": "success",
            "count": len(alerts),
            "alerts": alerts,
        }
    except Exception as exc:
        logger.error("Failed to fetch alerts: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

from services.dashboard_service import update_alert_status

@router.get("/assembly-lines")
async def handle_assembly_lines():
    """Return all existing production process/assembly line names from the Knowledge Graph."""
    try:
        lines = get_assembly_lines()
        return {"status": "success", "assembly_lines": lines}
    except Exception as exc:
        logger.error("Failed to fetch assembly lines: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


class AssignMaterialRequest(BaseModel):
    material: str
    process: str
    alert_id: str | None = None
    safety_stock: int | None = None


@router.post("/assign-material-process")
async def handle_assign_material_process(req: AssignMaterialRequest):
    """Assign a material to an assembly line and optionally mark the alert as read."""
    try:
        result = assign_material_to_process(req.material, req.process, req.safety_stock, req.alert_id)
        if req.alert_id:
            update_alert_status(req.alert_id, "DISMISSED")
        return result
    except Exception as exc:
        logger.error("Failed to assign material to process: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/request-fallback")
async def handle_request_fallback(req: FallbackRequest):
    """Create an urgent fallback supplier request alert."""
    try:
        return create_fallback_request_alert(req.material, req.risk_percent)
    except Exception as exc:
        logger.error("Failed to create fallback request alert: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/alerts/mark-read")
async def mark_alert_read(req: AlertStatusUpdate):
    try:
        return update_alert_status(req.alert_id, "READ")
    except Exception as exc:
        logger.error("Failed to mark alert read: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/alerts/dismiss")
async def dismiss_alert(req: AlertStatusUpdate):
    try:
        return update_alert_status(req.alert_id, "DISMISSED")
    except Exception as exc:
        logger.error("Failed to dismiss alert: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/chat")
async def chat(question: dict):
    user_question = question.get("question", "").strip()
    if not user_question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    chat_history = question.get("chat_history", [])
    if not isinstance(chat_history, list):
        chat_history = []

    logger.info("Chat question: %.100s", user_question)

    try:
        state = await run_chat_pipeline_async(user_question, chat_history)
    except Exception as exc:
        logger.error("Chat pipeline crashed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Chat pipeline error: {exc}",
        )

    return {
        "status": "success",
        "answer": state.get("final_answer", ""),
        "sparql": state.get("generated_sparql", ""),
        "results": state.get("graph_results", []),
        "topic_accepted": state.get("is_valid_topic", False),
    }
