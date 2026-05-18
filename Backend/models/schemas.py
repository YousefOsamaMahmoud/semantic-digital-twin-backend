# ============================================================
# models/schemas.py
# Pydantic models for strict data validation.
#
# These schemas act as the "contract" between the frontend
# and the backend — if the JSON payload doesn't match,
# FastAPI will auto-reject it with a 422 error.
# ============================================================

import uuid

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


class ExtractedSLAData(BaseModel):
    """
    Schema representing structured data extracted from an SLA contract
    PDF by the LLM extraction pipeline.

    This is the raw output from the LangGraph extraction agent before
    human review. It contains detailed financial and logistical parameters
    parsed from the supplier contract document.

    Fields
    ------
    document_id : str
        Unique document reference number or auto-generated UUID.
    supplier_id : str
        The identifier or code of the supplier/vendor.
    supplier_name : str
        Human-readable name of the raw-material supplier.
    material : str
        The specific raw material covered by this SLA.
    sla_lead_time_hours : int
        The contractual delivery lead time expressed in hours.
    delay_penalty_rate : float
        Financial penalty amount per day (or unit) for delayed delivery.
    missed_item_penalty_rate : float
        Penalty amount per individual unit that is missing/short-shipped.
    minimum_quality_threshold : float
        Minimum acceptable quality yield as a decimal (e.g., 0.98 = 98%).
    quality_penalty_rate : float
        Penalty rate for quality below the threshold, as a decimal (e.g., 0.15 = 15%).
    """

    document_id: str = Field(
        default_factory=lambda: f"EXT-{uuid.uuid4().hex[:12].upper()}",
        examples=["EXT-A1B2C3D4E5F6"],
        description="Unique document reference or auto-generated extraction ID",
    )
    supplier_id: str = Field(
        ...,
        min_length=1,
        examples=["SUP_001"],
        description="Supplier/vendor identifier code",
    )
    supplier_name: str = Field(
        ...,
        min_length=1,
        examples=["Steel Co"],
        description="Human-readable name of the supplier",
    )
    material: str = Field(
        ...,
        min_length=1,
        examples=["Steel_Coil"],
        description="Specific raw material covered under this SLA",
    )
    sla_lead_time_hours: int = Field(
        ...,
        gt=0,
        examples=[72],
        description="Contractual delivery lead time in hours",
    )
    delay_penalty_rate: float = Field(
        ...,
        ge=0.0,
        examples=[500.0],
        description="Financial penalty amount for delayed delivery (per day/unit)",
    )
    missed_item_penalty_rate: float = Field(
        ...,
        ge=0.0,
        examples=[150.0],
        description="Penalty amount per missing/short-shipped item",
    )
    minimum_quality_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        examples=[0.95],
        description="Minimum acceptable quality yield as a decimal (0.0–1.0)",
    )
    quality_penalty_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        examples=[0.10],
        description="Penalty rate for sub-quality materials as a decimal (0.0–1.0)",
    )


class ConfirmedSLA(BaseModel):
    """
    Schema representing a human-reviewed and confirmed SLA contract.

    After the LLM extracts structured data from the PDF, a human
    (Procurement Manager) reviews and potentially corrects the fields.
    This model captures the final approved version that will be
    persisted as RDF triples in GraphDB.

    Fields
    ------
    extraction_id : str
        Links back to the original extraction trace ID.
    supplier_name : str
        The name of the raw-material supplier (human-verified).
    material : str
        The specific raw material covered by this SLA (human-verified).
    lead_time_days : int
        Delivery lead time in days (converted from hours or manually edited).
    penalty_clause : str
        Free-text penalty description (human-edited).
    corrections : str | None
        Optional notes from the reviewer about what was corrected.
    """

    extraction_id: str = Field(
        ...,
        examples=["EXT-A1B2C3D4E5F6"],
        description="UUID linking back to the original LLM extraction trace",
    )
    supplier_name: str = Field(
        ...,
        min_length=1,
        examples=["Acme Steel Corp"],
        description="Name of the raw-material supplier (human-verified)",
    )
    material: str = Field(
        ...,
        min_length=1,
        examples=["Cold-Rolled Steel"],
        description="Raw material covered by this SLA (human-verified)",
    )
    lead_time_days: int = Field(
        ...,
        gt=0,
        examples=[3],
        description="Converted from hours or manually edited by the human reviewer",
    )
    penalty_clause: str = Field(
        ...,
        min_length=1,
        examples=["2% deduction per day of delay"],
        description="Penalty clause text for SLA violations (human-edited)",
    )
    corrections: str | None = Field(
        default=None,
        examples=["Corrected lead time from 72h to 3 days; adjusted penalty rate"],
        description="Optional notes from the reviewer about what was corrected",
    )


class RiskAnalysisResult(BaseModel):
    """
    Schema representing the output of the LLM-based risk analyst agent.

    The multi-agent risk engine analyses delivery context (IoT telemetry,
    GraphDB ontology inferences, inventory levels, SLA terms) and produces
    a structured risk assessment with severity classification, confidence
    scoring, and financial impact estimation.

    Fields
    ------
    risks : list[str]
        List of active risk types detected (e.g., DelayEvent, SLAViolation).
    confidence : float
        Confidence score of the analysis between 0.0 and 1.0.
    severity : str
        Classified severity level: Low, Medium, High, or Critical.
    financial_penalty_estimate : float
        Estimated financial penalty amount based on SLA terms.
    reasoning : str
        Detailed explanation text from the multi-agent reasoning pipeline.
    """

    risks: list[str] = Field(
        ...,
        examples=[["DelayEvent", "SLAViolation"]],
        description="List of active risk types detected by the analysis engine",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        examples=[0.85],
        description="Confidence score of the analysis from 0.0 to 1.0",
    )
    severity: str = Field(
        ...,
        examples=["High"],
        description="Severity level: Low, Medium, High, or Critical",
    )
    financial_penalty_estimate: float = Field(
        ...,
        ge=0.0,
        examples=[12500.0],
        description="Estimated financial penalty amount in USD",
    )
    reasoning: str = Field(
        ...,
        examples=["48h delay exceeds 72h SLA lead time. Inventory below safety stock. Production disruption probable."],
        description="Detailed explanation from the multi-agent reasoning pipeline",
    )


class IoTTelemetryEvent(BaseModel):
    """
    Schema representing an IoT telemetry event from the supply chain.

    This is the input trigger for the multi-agent risk engine pipeline.
    It captures real-time (or simulated) IoT data about a delivery
    including delay estimates, disruption probability, and reason codes.

    Fields
    ------
    delivery_id : str
        The unique identifier of the delivery/truck shipment.
    estimated_delay_hours : int
        ML-predicted or IoT-reported delay duration in hours.
    reason_code : str
        Machine-readable code describing the delay reason.
    disruption_probability : float
        Probability score that this delay will cause disruption (0.0–1.0).
    timestamp : str
        ISO 8601 timestamp of when the telemetry event was recorded.
    """

    delivery_id: str = Field(
        ...,
        min_length=1,
        examples=["DEL_001"],
        description="Unique identifier of the delivery or shipment",
    )
    estimated_delay_hours: int = Field(
        ...,
        ge=0,
        examples=[48],
        description="Estimated delay duration in hours from IoT/ML prediction",
    )
    reason_code: str = Field(
        ...,
        examples=["Weather_Delay"],
        description="Machine-readable reason code for the delay event",
    )
    disruption_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        examples=[0.90],
        description="Probability score that this delay will disrupt production (0.0–1.0)",
    )
    timestamp: str = Field(
        ...,
        examples=["2026-03-05T15:30:00Z"],
        description="ISO 8601 timestamp of the telemetry event",
    )


class ManagerAlert(BaseModel):
    """
    Schema representing a manager-level alert generated by the risk engine.

    After the multi-agent pipeline analyses risks and determines which
    managers should be notified, it generates targeted alert messages
    for each relevant role. This model captures the alert content and
    its validation status.

    Fields
    ------
    manager_title : str
        The target manager role: Production Manager, Procurement Manager,
        or Logistics Manager.
    alert_text : str
        The generated alert message body.
    validated : bool
        Whether the alert passed the validator agent's quality check.
    """

    manager_title: str = Field(
        ...,
        examples=["Production Manager"],
        description="Target manager role: Production Manager, Procurement Manager, or Logistics Manager",
    )
    alert_text: str = Field(
        ...,
        min_length=1,
        examples=["Delivery DEL_001 is delayed by 48h due to Weather_Delay. Assembly line stoppage probable within 24h."],
        description="Alert message body generated by the multi-agent pipeline",
    )
    validated: bool = Field(
        default=False,
        description="Whether this alert passed the validator agent quality gate",
    )
