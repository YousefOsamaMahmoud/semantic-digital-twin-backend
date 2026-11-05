"""
generate_telemetry_stream.py

Generates a larger, realistic synthetic telemetry stream in the exact
same JSON shape as the sample file provided by the team lead
(telemetry_stream_logistics.json), for the 5 known deliveries that
already exist in the project's ontology.

Run it once to (re)create Data_Science/data_Lake/telemetry_stream_logistics.json
with many records instead of just 1.

Usage:
    python generate_telemetry_stream.py
    python generate_telemetry_stream.py --count 500 --output custom_path.json
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------
# Known deliveries (must match the individuals already loaded into
# GraphDB from Data_Science/ontology/*.rdf) plus a route/carrier
# naming convention copied from the sample record.
# ----------------------------------------------------------------
DELIVERIES = [
    {
        "delivery_id": "Delivery_VoltSupply_Main",
        "route_id": "Route_VoltSupply_001",
        "carrier_3pl": "3PL_VoltSupply_Main",
        "base_lat": 30.06, "base_lon": -113.50,
    },
    {
        "delivery_id": "Delivery_VoltSupply_Shortage",
        "route_id": "Route_VoltSupply_002",
        "carrier_3pl": "3PL_VoltSupply_Express",
        "base_lat": 29.95, "base_lon": -112.80,
    },
    {
        "delivery_id": "Delivery_Apex_Delayed",
        "route_id": "Route_Apex_001",
        "carrier_3pl": "3PL_Apex_Freight",
        "base_lat": 33.45, "base_lon": -111.94,
    },
    {
        "delivery_id": "Delivery_AuraSteel_Delayed",
        "route_id": "Route_AuraSteel_001",
        "carrier_3pl": "3PL_AuraSteel_Logistics",
        "base_lat": 41.88, "base_lon": -87.63,
    },
    {
        "delivery_id": "Delivery_EcoLithium_Quality",
        "route_id": "Route_EcoLithium_001",
        "carrier_3pl": "3PL_EcoLithium_Transport",
        "base_lat": 34.05, "base_lon": -118.24,
    },
]

WEATHER_CONDITIONS = ["Clear", "Rain", "Storm", "Fog", "Snow", "Wind"]
STATUS_CODES = ["Shipped", "In_Transit", "At_Port", "Customs_Hold", "Delayed", "Delivered"]
RISK_STATUSES = ["None", "Potential", "Confirmed"]

# Weather -> plausible disruption probability range, so a "Storm"
# event is statistically more likely to carry a high risk score than
# a "Clear" one (keeps the synthetic data internally consistent).
WEATHER_RISK_RANGE = {
    "Clear": (0.02, 0.25),
    "Wind": (0.10, 0.40),
    "Fog": (0.15, 0.50),
    "Rain": (0.20, 0.60),
    "Snow": (0.30, 0.75),
    "Storm": (0.55, 0.97),
}


def _random_status_for_risk(disruption_probability: float) -> tuple[str, str]:
    """Pick a (status_code, risk_status) pair consistent with the probability."""
    if disruption_probability >= 0.7:
        status = random.choice(["Delayed", "Customs_Hold", "At_Port"])
        risk = "Confirmed"
    elif disruption_probability >= 0.4:
        status = random.choice(["In_Transit", "At_Port", "Shipped"])
        risk = "Potential"
    else:
        status = random.choice(["Shipped", "In_Transit", "Delivered"])
        risk = "None"
    return status, risk


def generate_event(delivery: dict, timestamp: datetime) -> dict:
    weather = random.choice(WEATHER_CONDITIONS)
    low, high = WEATHER_RISK_RANGE[weather]
    disruption_probability = round(random.uniform(low, high), 2)

    status_code, risk_status = _random_status_for_risk(disruption_probability)

    # Vehicles stopped/delayed tend to have near-zero speed; healthy
    # in-transit shipments have plausible highway speeds.
    if status_code in ("Customs_Hold", "At_Port", "Delivered"):
        speed = 0.0
    elif status_code == "Delayed":
        speed = round(random.uniform(0, 20), 1)
    else:
        speed = round(random.uniform(40, 110), 1)

    return {
        "discovery_timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "delivery_id": delivery["delivery_id"],
        "route_id": delivery["route_id"],
        "carrier_3pl": delivery["carrier_3pl"],
        "gps_location": {
            "lat": round(delivery["base_lat"] + random.uniform(-0.8, 0.8), 4),
            "lon": round(delivery["base_lon"] + random.uniform(-0.8, 0.8), 4),
        },
        "current_speed_kmh": speed,
        "cargo_temp_celsius": round(random.uniform(2.0, 28.0), 1),
        "status_code": status_code,
        "weather_condition": weather,
        "risk_status": risk_status,
        "disruption_probability": disruption_probability,
    }


def generate_stream(count: int, interval_minutes: int) -> list[dict]:
    """
    Generate `count` events, evenly spaced `interval_minutes` apart,
    ending at "now" (UTC) and going backwards — so the most recent
    record is the freshest simulated reading.
    """
    now = datetime.now(timezone.utc)
    events = []
    for i in range(count):
        delivery = random.choice(DELIVERIES)
        timestamp = now - timedelta(minutes=interval_minutes * (count - i))
        events.append(generate_event(delivery, timestamp))
    return events


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic logistics telemetry stream data.")
    parser.add_argument("--count", type=int, default=300, help="Number of telemetry records to generate.")
    parser.add_argument("--interval-minutes", type=int, default=15, help="Minutes between consecutive readings.")
    parser.add_argument(
        "--output",
        type=str,
        default="../Data_Science/data_Lake/iot_streams/telemetry_stream_logistics.json",
        help="Output JSON file path.",
    )
    args = parser.parse_args()

    events = generate_stream(args.count, args.interval_minutes)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

    print(f"Generated {len(events)} telemetry records -> {args.output}")


if __name__ == "__main__":
    main()
