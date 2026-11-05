# ============================================================
# services/telemetry_simulator_service.py — Layer 2: Telemetry Simulator
#
# Background task that streams REAL telemetry records from
# Data_Science/data_Lake/telemetry_stream_logistics.json (provided by
# the team lead / generated via Backend/generate_telemetry_stream.py)
# and feeds each one through the existing 7-node risk engine pipeline
# (services/risk_engine_service.process_iot_event).
#
# This is what makes the platform feel "live": instead of a human
# manually POSTing to /api/sandbox/simulate-iot, this loop replays
# the telemetry stream automatically, one record every
# TELEMETRY_INTERVAL_SECONDS, looping back to the start once the
# stream is exhausted.
#
# Raw telemetry record shape (see telemetry_stream_logistics.json):
#   {
#     "discovery_timestamp": "...", "delivery_id": "...",
#     "route_id": "...", "carrier_3pl": "...",
#     "gps_location": {"lat": .., "lon": ..},
#     "current_speed_kmh": .., "cargo_temp_celsius": ..,
#     "status_code": "...", "weather_condition": "...",
#     "risk_status": "...", "disruption_probability": ..
#   }
#
# The risk engine pipeline expects an IoTTelemetryEvent
# (delivery_id, estimated_delay_hours, reason_code,
# disruption_probability, timestamp) — _to_iot_event() below
# translates one raw record into that shape, deriving the missing
# estimated_delay_hours from status_code/speed/disruption_probability.
# ============================================================

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from models.schemas import IoTTelemetryEvent
from services.risk_engine_service import process_iot_event

logger = logging.getLogger(__name__)

# --------------------------------------------------------------
# Configuration
# --------------------------------------------------------------

# Path to the real telemetry data file. Configurable via .env in
# case the data lake path ever moves.
TELEMETRY_STREAM_PATH = Path(
    os.getenv(
        "TELEMETRY_STREAM_PATH",
        str(Path(__file__).resolve().parent.parent.parent / "Data_Science" / "data_Lake" / "iot_streams" / "telemetry_stream_logistics.json"),
    )
)

# Path to the trained Logistics delay-prediction model (see
# Backend/train_logistics_model.py). Falls back to the simpler
# rule-based estimate in _estimate_delay_hours_fallback() if this
# file isn't present, so the simulator never hard-crashes for lack
# of a model.
LOGISTICS_MODEL_PATH = Path(
    os.getenv(
        "LOGISTICS_MODEL_PATH",
        str(Path(__file__).resolve().parent.parent / "models" / "ml_assets" / "logistics_delay_model.pkl"),
    )
)
LOGISTICS_FEATURES_PATH = Path(
    os.getenv(
        "LOGISTICS_FEATURES_PATH",
        str(Path(__file__).resolve().parent.parent / "models" / "ml_assets" / "logistics_model_features.json"),
    )
)

# Interval between replayed events, in seconds. Configurable via
# .env so it can be slowed down/sped up without a code change.
TELEMETRY_INTERVAL_SECONDS = float(os.getenv("TELEMETRY_INTERVAL_SECONDS", "30"))

# Status codes that imply the shipment is actively stalled/blocked —
# used by the rule-based fallback estimate.
_STALLED_STATUS_CODES = {"Customs_Hold", "Delayed", "At_Port"}

# Maps the telemetry stream's categorical weather label onto the
# trained model's 0-1 weather_condition_severity feature. This is an
# honest approximation, not a measured value — the telemetry file
# doesn't carry a continuous severity score.
_WEATHER_SEVERITY = {
    "Clear": 0.05,
    "Wind": 0.30,
    "Fog": 0.45,
    "Rain": 0.55,
    "Snow": 0.70,
    "Storm": 0.90,
}

# Maps status_code onto the model's 0-1 route_risk_level feature,
# same honest-approximation caveat as above.
_STATUS_ROUTE_RISK = {
    "Delivered": 0.05,
    "Shipped": 0.20,
    "In_Transit": 0.30,
    "At_Port": 0.55,
    "Customs_Hold": 0.75,
    "Delayed": 0.90,
}

# --------------------------------------------------------------
# Defaults for the features the real trained model expects that the
# raw telemetry stream has NO equivalent for at all (no warehouse,
# cost, demand-history, or cargo-condition data is captured by these
# GPS/sensor-style records). Fixed at a plausible neutral value so
# the model still runs end-to-end — but these are honestly NOT real
# signal, just neutral placeholders.
# --------------------------------------------------------------
_DEFAULTED_FEATURES = {
    "eta_variation_hours": 3.0,
    "customs_clearance_time": 6.0,
    "loading_unloading_time": 1.5,
    "port_congestion_level": 0.4,
    "lead_time_days": 7.0,
    "fuel_consumption_rate": 10.0,
    "supplier_reliability_score": 0.7,
    "handling_equipment_availability": 0.7,
    "driver_behavior_score": 0.7,
    "order_fulfillment_status": 0.7,
    "fatigue_monitoring_score": 0.7,
    "warehouse_inventory_level": 500.0,
    "shipping_costs": 250.0,
    "historical_demand": 500.0,
    "cargo_condition_status": 0.8,
}

# Module-level handle to the running background task so it can be
# cancelled cleanly on application shutdown.
_simulator_task: asyncio.Task | None = None

# Lazily-loaded model + its expected feature order. Stay None until
# the first call to _load_logistics_model() succeeds (or definitively
# fails, logging why) — callers fall back to the simple rule-based
# estimate whenever this is unavailable.
_LOGISTICS_MODEL = None
_LOGISTICS_FEATURES: list[str] | None = None
_LOGISTICS_MODEL_LOAD_ATTEMPTED = False


def _load_logistics_model() -> None:
    """
    Lazily load the trained Logistics delay model + its expected
    feature list, once. Safe to call repeatedly — only does real work
    on the first call.
    """
    global _LOGISTICS_MODEL, _LOGISTICS_FEATURES, _LOGISTICS_MODEL_LOAD_ATTEMPTED
    if _LOGISTICS_MODEL_LOAD_ATTEMPTED:
        return
    _LOGISTICS_MODEL_LOAD_ATTEMPTED = True

    if not LOGISTICS_MODEL_PATH.exists() or not LOGISTICS_FEATURES_PATH.exists():
        logger.warning(
            "[Telemetry Simulator] Trained logistics model not found at %s — "
            "falling back to the rule-based delay estimate. Run "
            "Backend/train_logistics_model.py to generate it.",
            LOGISTICS_MODEL_PATH,
        )
        return

    try:
        _LOGISTICS_MODEL = joblib.load(LOGISTICS_MODEL_PATH)
        with open(LOGISTICS_FEATURES_PATH, "r", encoding="utf-8") as f:
            _LOGISTICS_FEATURES = json.load(f)
        logger.info(
            "[Telemetry Simulator] Loaded trained logistics model from %s (%d features expected).",
            LOGISTICS_MODEL_PATH,
            len(_LOGISTICS_FEATURES),
        )
    except Exception as exc:
        logger.error(
            "[Telemetry Simulator] Failed to load logistics model: %s. Falling back to rule-based estimate.",
            exc,
        )
        _LOGISTICS_MODEL = None
        _LOGISTICS_FEATURES = None


def _load_telemetry_stream() -> list[dict[str, Any]]:
    """
    Load the real telemetry records from disk. Returns an empty list
    (rather than raising) if the file is missing, so the app still
    starts up cleanly and logs a clear, actionable warning instead
    of crashing.
    """
    if not TELEMETRY_STREAM_PATH.exists():
        logger.warning(
            "[Telemetry Simulator] Stream file not found at %s — "
            "the simulator will stay idle. Run "
            "Backend/generate_telemetry_stream.py to create it.",
            TELEMETRY_STREAM_PATH,
        )
        return []

    try:
        with open(TELEMETRY_STREAM_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            logger.error("[Telemetry Simulator] Expected a JSON array in %s, got %s.", TELEMETRY_STREAM_PATH, type(records))
            return []
        logger.info("[Telemetry Simulator] Loaded %d real telemetry records from %s.", len(records), TELEMETRY_STREAM_PATH)
        return records
    except Exception as exc:
        logger.error("[Telemetry Simulator] Failed to load %s: %s", TELEMETRY_STREAM_PATH, exc)
        return []


def _estimate_delay_hours_fallback(record: dict[str, Any]) -> int:
    """
    Rule-based delay estimate, used only when the trained logistics
    model isn't available. Kept as a safety net so the simulator
    never breaks if the .pkl file is missing or fails to load.
    """
    status_code = record.get("status_code", "")
    speed = record.get("current_speed_kmh", 0.0) or 0.0
    probability = record.get("disruption_probability", 0.0) or 0.0

    if status_code == "Delivered":
        return 0

    if status_code in _STALLED_STATUS_CODES or speed == 0.0:
        base = 12
        scaled = int(base + probability * 84)
        return max(1, scaled)

    return max(0, int(probability * 24))


def _build_model_feature_row(record: dict[str, Any]) -> "pd.DataFrame":
    """
    Build the exact 19-column row the trained logistics model expects,
    from one raw telemetry record.

    HONEST LIMITATION: the telemetry stream only carries real signal
    for ~4 of the 19 trained features (disruption_probability, the
    weather/status-derived severity scores, and the timestamp parts).
    The remaining 11 (procurement lead time, driver behavior, fuel
    consumption, etc.) have no equivalent in this data source at all,
    so they're filled with fixed neutral defaults from
    _DEFAULTED_FEATURES. The model still runs and returns a real
    prediction, but its accuracy is bounded by how much of its input
    is genuine vs. placeholder — see _DEFAULTED_FEATURES' docstring.
    """
    import pandas as pd

    status_code = record.get("status_code", "")
    weather = record.get("weather_condition", "Clear")
    speed = float(record.get("current_speed_kmh", 0.0) or 0.0)
    probability = float(record.get("disruption_probability", 0.0) or 0.0)
    gps = record.get("gps_location", {}) or {}
    cargo_temp = float(record.get("cargo_temp_celsius", 15.0) or 15.0)

    try:
        ts = datetime.fromisoformat(record.get("discovery_timestamp", "").replace("Z", "+00:00"))
    except Exception:
        ts = datetime.utcnow()

    # Real-signal features
    row = {
        "disruption_likelihood_score": probability,
        "weather_condition_severity": _WEATHER_SEVERITY.get(weather, 0.4),
        "route_risk_level": _STATUS_ROUTE_RISK.get(status_code, 0.4),
        # Stopped/near-zero speed implies heavier traffic/congestion
        # on the current leg of the route.
        "traffic_congestion_level": 0.85 if speed == 0.0 else max(0.0, min(1.0, 1.0 - (speed / 110.0))),
        "vehicle_gps_latitude": float(gps.get("lat", 0.0) or 0.0),
        "vehicle_gps_longitude": float(gps.get("lon", 0.0) or 0.0),
        "iot_temperature": cargo_temp,
        "month": ts.month,
        "day": ts.day,
        "hour": ts.hour,
        "dayofweek": ts.weekday(),
    }

    # Defaulted features — no real signal available, see docstring above.
    row.update(_DEFAULTED_FEATURES)

    return pd.DataFrame([row])


def _estimate_delay_hours_via_model(record: dict[str, Any]) -> float | None:
    """
    Run the real trained logistics model on one telemetry record.
    Returns None (rather than raising) if the model isn't loaded or
    the prediction fails for any reason, so the caller can fall back
    to the rule-based estimate cleanly.
    """
    _load_logistics_model()
    if _LOGISTICS_MODEL is None or _LOGISTICS_FEATURES is None:
        return None

    try:
        row = _build_model_feature_row(record)
        row = row[_LOGISTICS_FEATURES]  # enforce exact column order the model was trained on
        prediction = _LOGISTICS_MODEL.predict(row)[0]
        # The model predicts `delivery_time_deviation` on a [-2, 10]
        # scale (hours of deviation from schedule, can be negative =
        # early). Clamp to a non-negative delay-hours value for the
        # alert pipeline, which only expects "how many hours late".
        return max(0.0, float(prediction))
    except Exception as exc:
        logger.warning("[Telemetry Simulator] Logistics model prediction failed (%s); using rule-based fallback.", exc)
        return None


def _estimate_delay_hours(record: dict[str, Any]) -> int:
    """
    Real delay estimate for one telemetry record. Tries the trained
    ML model first; falls back to the simple rule-based estimate if
    the model is unavailable or prediction fails for any reason.
    """
    if record.get("status_code") == "Delivered":
        return 0

    model_prediction = _estimate_delay_hours_via_model(record)
    if model_prediction is not None:
        return max(1, int(round(model_prediction)))

    return _estimate_delay_hours_fallback(record)


def _reason_code_from_record(record: dict[str, Any]) -> str:
    """
    Build a machine-readable reason code from the most relevant raw
    field(s) — prefers weather when it's the likely driver, falls
    back to the status code otherwise.
    """
    status_code = record.get("status_code", "")
    weather = record.get("weather_condition", "")

    if status_code == "Delivered":
        return "No_Disruption"
    if weather and weather not in ("Clear",):
        return f"Weather_{weather}"
    if status_code:
        return status_code
    return "Unknown"


def _to_iot_event(record: dict[str, Any]) -> IoTTelemetryEvent:
    """Translate one raw telemetry record into the schema the risk engine pipeline expects."""
    return IoTTelemetryEvent(
        delivery_id=record["delivery_id"],
        estimated_delay_hours=_estimate_delay_hours(record),
        reason_code=_reason_code_from_record(record),
        disruption_probability=float(record.get("disruption_probability", 0.0)),
        timestamp=record.get("discovery_timestamp") or record.get("timestamp", ""),
    )


async def _simulation_loop() -> None:
    """
    Core loop: every TELEMETRY_INTERVAL_SECONDS, replay the next real
    telemetry record from the stream file through the full risk engine
    pipeline (GraphDB injection -> context fetch -> LLM risk analysis
    -> manager routing -> alert generation -> validation ->
    persistence). Loops back to the beginning once exhausted, so the
    "live" demo never runs dry.
    """
    records = _load_telemetry_stream()

    if not records:
        logger.warning(
            "[Telemetry Simulator] No telemetry records available — "
            "loop will idle and recheck every %.0fs in case the file "
            "appears later.",
            TELEMETRY_INTERVAL_SECONDS,
        )
        while not records:
            await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)
            records = _load_telemetry_stream()

    logger.info(
        "[Telemetry Simulator] Starting background loop (interval=%.0fs, %d real records queued).",
        TELEMETRY_INTERVAL_SECONDS,
        len(records),
    )

    index = 0
    while True:
        try:
            record = records[index % len(records)]
            event = _to_iot_event(record)
            used_model = "ML model" if _LOGISTICS_MODEL is not None else "rule-based fallback"

            logger.info(
                "[Telemetry Simulator] Emitting record %d/%d: delivery=%s, delay=%dh (%s), reason=%s, prob=%.2f",
                (index % len(records)) + 1,
                len(records),
                event.delivery_id,
                event.estimated_delay_hours,
                used_model,
                event.reason_code,
                event.disruption_probability,
            )
            alert = await process_iot_event(event)
            logger.info(
                "[Telemetry Simulator] Pipeline produced alert for %s.",
                alert.manager_title,
            )
        except asyncio.CancelledError:
            logger.info("[Telemetry Simulator] Loop cancelled, shutting down cleanly.")
            raise
        except Exception as exc:
            # Never let one bad record kill the whole background loop —
            # log it and keep the stream alive for the next tick.
            logger.error("[Telemetry Simulator] Iteration failed: %s", exc)

        index += 1
        await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)


def start_simulator() -> None:
    """
    Launch the simulator as a background asyncio task. Safe to call
    once at application startup. No-op if already running.
    """
    global _simulator_task
    if _simulator_task is not None and not _simulator_task.done():
        logger.warning("[Telemetry Simulator] start_simulator() called but loop is already running.")
        return
    _simulator_task = asyncio.create_task(_simulation_loop())


def stop_simulator() -> None:
    """Cancel the background simulator task cleanly on app shutdown."""
    global _simulator_task
    if _simulator_task is not None and not _simulator_task.done():
        _simulator_task.cancel()
        logger.info("[Telemetry Simulator] Stop requested.")
    _simulator_task = None

