# ============================================================
# api/sandbox.py — Layer 1: Controller / API Router
#
# This module defines the SLA Sandbox endpoints.
# It is ONLY responsible for:
#   1. Receiving the HTTP request
#   2. Validating the payload (via Pydantic)
#   3. Calling the service layers
#   4. Returning the HTTP response
#
# It contains ZERO business logic — all intelligence lives
# in the services/ layer.
# ============================================================

import asyncio
import io
import logging

import pdfplumber
try:
    import docx  # python-docx
except ImportError:
    docx = None
from fastapi import APIRouter, File, HTTPException, UploadFile

from models.schemas import ConfirmedSLA, IoTTelemetryEvent, ManagerAlert, SLAContract, OrderRiskPredictionRequest, OrderRiskPredictionResponse
from services.dashboard_service import get_impacted_products, invalidate_impacted_cache, get_assembly_line_for_material
from services.lifting_service import persist_confirmed_sla, save_sla_contract, to_sla_contract
from services.llm_service import run_extraction_pipeline
from services.risk_engine_service import process_iot_event

from services.order_risk_service import predict_order_risk

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sandbox",
    tags=["SLA Sandbox"],
)


@router.get("/match-assembly-line")
async def match_assembly_line(material: str):
    """
    Check if a material already exists in the Knowledge Graph with a linked assembly line.
    Returns { matched: true, process: 'ProcessName' } or { matched: false }.
    """
    try:
        process = get_assembly_line_for_material(material)
        if process:
            return {"matched": True, "process": process}
        return {"matched": False, "process": None}
    except Exception as exc:
        logger.error("match-assembly-line error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        raise ValueError(f"Failed to read PDF: {exc}") from exc

    raw = "\n".join(pages_text).strip()
    if not raw:
        raise ValueError(
            "The uploaded PDF appears to be empty or contains no "
            "extractable text.  Ensure the file is a text-based PDF, "
            "not a scanned image-only document."
        )
    return raw


def _extract_text_from_txt(file_bytes: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            raw = file_bytes.decode(enc).strip()
            if raw:
                return raw
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode the text file. Ensure it is UTF-8 or Latin-1 encoded.")


def _extract_text_from_docx(file_bytes: bytes) -> str:
    if docx is None:
        raise ValueError("python-docx is not installed. Run: pip install python-docx")
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        raw = "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception as exc:
        raise ValueError(f"Failed to read DOCX: {exc}") from exc
    if not raw:
        raise ValueError("The DOCX file appears to be empty or contains no extractable text.")
    return raw


def _extract_text(file_bytes: bytes, filename: str) -> str:
    """Dispatch text extraction based on file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return _extract_text_from_pdf(file_bytes)
    if ext == "txt":
        return _extract_text_from_txt(file_bytes)
    if ext in ("doc", "docx"):
        return _extract_text_from_docx(file_bytes)
    raise ValueError(f"Unsupported file type '.{ext}'. Accepted formats: PDF, TXT, DOC, DOCX.")


@router.post("/upload-sla")
async def upload_sla(contract: SLAContract):
    try:
        loop = asyncio.get_running_loop()
        graph_result = await loop.run_in_executor(None, save_sla_contract, contract)

        return {
            "status": "success",
            "message": (
                f"SLA contract saved to GraphDB. "
                f"Inserted: ({graph_result['supplier']})"
                f" :supplies ({graph_result['material']})"
            ),
            "graph_data": graph_result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to save SLA contract to GraphDB. "
                f"Reason: {str(e)}"
            ),
        )



@router.post("/upload-transactions")
async def upload_transactions(file: UploadFile = File(...)):
    logger.info("Received transactions upload file: %s (content_type=%s)", file.filename, file.content_type)
    
    try:
        contents = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read uploaded file: {exc}",
        )
        
    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )
        
    try:
        from services.supplier_evaluator_service import evaluate_and_update_suppliers
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, evaluate_and_update_suppliers, contents, file.filename
        )
        
        # Clear dashboard cache so the new scores are immediately fetched
        invalidate_impacted_cache()
        
        return result
        
    except Exception as e:
        logger.error("Failed to process transaction sheet: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation pipeline failed: {str(e)}",
        )


@router.get("/impacted-products")
async def get_impacted_products_endpoint():
    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, get_impacted_products)

        return {
            "status": "success",
            "count": len(results),
            "impacted_products": results,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to query impacted products from GraphDB. "
                f"Reason: {str(e)}"
            ),
        )


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    logger.info("Received file: %s (content_type=%s)", file.filename, file.content_type)

    try:
        contents = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read uploaded file: {exc}",
        )

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    try:
        raw_text = _extract_text(contents, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Extracted %d characters from %s.", len(raw_text), file.filename)

    try:
        loop = asyncio.get_running_loop()
        state = await loop.run_in_executor(None, run_extraction_pipeline, raw_text)
    except Exception as exc:
        logger.error("Extraction pipeline crashed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"LLM extraction pipeline encountered an unexpected error: {exc}",
        )

    if not state.get("is_valid_contract", False):
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded document was not recognised as a valid "
                "supply-chain SLA contract.  Please verify the file "
                "and try again."
            ),
        )

    extracted_data = state.get("extracted_data")

    if extracted_data is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "LLM extraction failed after the maximum number of "
                "retries.  The contract text may be ambiguous or "
                "incomplete.  Please review the document and try again."
            ),
        )

    mapped = to_sla_contract(extracted_data)

    return {
        "status": "success",
        "extraction_id": state.get("document_id", ""),
        "extracted_data": extracted_data.model_dump(),
        "mapped_sla": mapped.model_dump(),
        "raw_text": raw_text,
    }


@router.post("/confirm-sla")
async def confirm_sla(confirmed: ConfirmedSLA):
    logger.info(
        "Confirming SLA: extraction=%s, supplier=%s, material=%s",
        confirmed.extraction_id,
        confirmed.supplier_name,
        confirmed.material,
    )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, persist_confirmed_sla, confirmed)
        invalidate_impacted_cache()
    except Exception as exc:
        logger.error("Failed to persist confirmed SLA: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save the confirmed SLA to GraphDB: {exc}",
        )

    return {
        "status": "success",
        "extraction_id": confirmed.extraction_id,
        "supplier": confirmed.supplier_name,
        "material": confirmed.material,
        "graph": result.get("graph", ""),
        "triples_inserted": result.get("triples_inserted", 0),
    }


@router.post("/simulate-iot", response_model=ManagerAlert)
async def simulate_iot_event(event: IoTTelemetryEvent):
    logger.info(
        "Simulating IoT event: delivery=%s, delay=%dh, reason=%s",
        event.delivery_id,
        event.estimated_delay_hours,
        event.reason_code,
    )

    try:
        alert: ManagerAlert = await process_iot_event(event)
    except Exception as exc:
        logger.error("Risk engine pipeline crashed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Risk assessment failed: {exc}",
        )

    return alert



@router.post("/predict-order-risk", response_model=OrderRiskPredictionResponse)
async def predict_order_planning_risk(request: OrderRiskPredictionRequest):
    """
    Evaluates risk of a proposed purchase order before placing it using the static ML model.
    """
    logger.info("Evaluating order planning risk for supplier: %s, material: %s", request.supplier_id, request.material_id)
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, predict_order_risk, request)
        return result
    except Exception as exc:
        logger.error("Order risk assessment crashed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Order risk evaluation failed: {exc}",
        )


@router.post("/place-order")
async def place_purchase_order(request: OrderRiskPredictionRequest):
    """
    Submits a new Purchase Order transaction:
      1. Saves the PO & Delivery individuals in GraphDB.
      2. Appends the order row as a new on-time transaction in the historical CSV dataset.
      3. Re-evaluates and updates all supplier scores.
    """
    logger.info("Placing new purchase order with supplier: %s, material: %s", request.supplier_id, request.material_id)
    try:
        from services.supplier_evaluator_service import record_placed_order_and_update_score
        loop = asyncio.get_running_loop()
        delivery_id = await loop.run_in_executor(
            None,
            record_placed_order_and_update_score,
            request.supplier_id,
            request.material_id,
            request.quantity,
            request.unit_price,
            request.po_date,
            request.po_type,
            request.department
        )
        if not delivery_id:
            raise HTTPException(status_code=500, detail="Failed to place order (dataset or context missing).")
            
        return {
            "status": "success",
            "message": f"Successfully placed order. Generated Delivery ID: {delivery_id}.",
            "delivery_id": delivery_id
        }
    except Exception as exc:
        logger.error("Order placement failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to place purchase order: {exc}"
        )


@router.post("/migrate-supplier-scores")
async def handle_migrate_supplier_scores():
    """
    Migration endpoint to initialize missing reliability scores for all existing suppliers.
    Assigns a default score of 0.75 to suppliers that don't have a score yet.
    """
    try:
        from knowledge_base import initialize_missing_supplier_scores
        result = initialize_missing_supplier_scores()
        return result
    except Exception as exc:
        logger.error("Supplier score migration failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to migrate supplier scores: {exc}"
        )
