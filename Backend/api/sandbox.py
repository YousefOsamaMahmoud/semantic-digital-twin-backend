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
from fastapi import APIRouter, File, HTTPException, UploadFile

from models.schemas import ConfirmedSLA, IoTTelemetryEvent, ManagerAlert, SLAContract
from services.dashboard_service import get_impacted_products
from services.lifting_service import persist_confirmed_sla, save_sla_contract, to_sla_contract
from services.llm_service import run_extraction_pipeline
from services.risk_engine_service import process_iot_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sandbox",
    tags=["SLA Sandbox"],
)


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
        raw_text = _extract_text_from_pdf(contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Extracted %d characters from PDF.", len(raw_text))

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
