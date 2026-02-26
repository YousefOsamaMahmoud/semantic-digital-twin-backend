# ============================================================
# models/schemas.py
# Pydantic models for strict data validation.
#
# These schemas act as the "contract" between the frontend
# and the backend — if the JSON payload doesn't match,
# FastAPI will auto-reject it with a 422 error.
# ============================================================

from pydantic import BaseModel, Field


class SLAContract(BaseModel):
    """
    Schema representing an SLA (Service-Level Agreement) contract
    extracted from a supplier's PDF document.

    Fields
    ------
    supplier_name : str
        The name of the raw-material supplier.
    material : str
        The specific raw material covered by this SLA.
    lead_time_days : int
        Maximum allowed delivery lead time (in days)
        before the SLA is considered breached.
    penalty_clause : str
        Free-text description of the financial penalty
        applied when the SLA is violated.
    """

    supplier_name: str = Field(
        ...,
        min_length=1,
        examples=["Acme Steel Corp"],
        description="Name of the raw-material supplier",
    )
    material: str = Field(
        ...,
        min_length=1,
        examples=["Cold-Rolled Steel"],
        description="Raw material covered by this SLA",
    )
    lead_time_days: int = Field(
        ...,
        gt=0,
        examples=[14],
        description="Max delivery lead time in days",
    )
    penalty_clause: str = Field(
        ...,
        min_length=1,
        examples=["2% deduction per day of delay"],
        description="Penalty clause text for SLA violations",
    )
