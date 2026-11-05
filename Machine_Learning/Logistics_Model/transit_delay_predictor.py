# =====================================================================
# Machine_Learning/transit_delay_predictor.py
#
# Real-Time Telemetry Stream Prediction Integration.
# This script:
#   1. Ingests simulated telemetry events from telemetry_stream_logistics.json.
#   2. Loads the pre-trained Logistics Model (Linear Regression pipeline)
#      and the expected feature names.
#   3. Queries GraphDB for the active delivery's supplier contract context
#      (SLA leadTimeDays, hasReliabilityScore).
#   4. Maps the dynamic telemetry fields and GraphDB properties into the
#      exact 26-column feature vector required by the model.
#   5. Runs inference to predict the actual delay hours directly.
#   6. Invokes the FastAPI backend endpoint /api/sandbox/simulate-iot
#      for flagged delays.
# =====================================================================

import os
import sys
import json
import pickle
import requests
import numpy as np
import pandas as pd

# Allow importing backend modules by adding the Backend folder to Python Path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BACKEND_PATH = os.path.join(PROJECT_ROOT, "Backend")
sys.path.append(BACKEND_PATH)

from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES

# File paths
MODEL_PATH = os.path.join(SCRIPT_DIR, "logistics_model.pkl")
FEATURES_PATH = os.path.join(SCRIPT_DIR, "logistics_features.json")
TELEMETRY_STREAM_PATH = os.path.join(PROJECT_ROOT, "Data_Science", "data_Lake", "iot_streams", "telemetry_stream_logistics.json")
BACKEND_URL = "http://localhost:8001/api/sandbox/simulate-iot"

def load_logistics_assets():
    """Loads the pre-trained logistics pipeline and features list."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(FEATURES_PATH):
        raise FileNotFoundError("Logistics model assets missing. Please run delay_predictor_logistics.py first.")

    with open(MODEL_PATH, "rb") as f:
        pipeline = pickle.load(f)
    
    with open(FEATURES_PATH, "r") as f:
        feature_names = json.load(f)
        
    return pipeline, feature_names

def query_graphdb_context(delivery_id: str) -> dict:
    """Queries GraphDB to fetch the static SLA contract properties for the delivery."""
    query = f"""{PREFIXES}
    SELECT ?leadTimeDays ?esgScore
    WHERE {{
        :{delivery_id} a :DeliveryEvent ;
                     :transports ?material .
        {{ ?supplier :supplies ?material }} UNION {{ ?material :isSuppliedBy ?supplier }}
        ?supplier :hasReliabilityScore ?esgScore .
        OPTIONAL {{ :{delivery_id} :leadTimeDays ?leadTimeDays }}
    }}
    LIMIT 1
    """
    results = graphdb.execute_sparql_select(query)
    if results:
        row = results[0]
        return {
            "lead_time_days": int(row.get("leadTimeDays", 1)),
            "supplier_reliability_score": float(row.get("esgScore", 0.5))
        }
    return None

def execute_stream_prediction(event: dict, pipeline, feature_names, debug=True):
    """Processes a single telemetry event, runs model prediction, and calls the API if delayed."""
    delivery_id = event["delivery_id"]
    status = event["status_code"]
    
    print(f"\n>> Ingested Telemetry for {delivery_id} | Status: {status} | Weather: {event['weather_condition']}")
    
    # Trigger prediction only if shipment is active and telemetry indicates an anomaly/stoppage
    is_active_shipment = status in ["Shipped", "In_Transit"]
    is_telemetry_anomaly = is_active_shipment and (
        event.get("weather_condition") in ["Storm", "Heavy Snow", "Windy"] or
        event.get("current_speed_kmh", 80.0) == 0.0 or
        event.get("disruption_probability", 0.0) > 0.50
    )
    
    if not is_telemetry_anomaly:
        print(f"    [+] Telemetry is nominal. No action needed.")
        return
        
    print(f"    [!] Telemetry anomaly detected (Weather: {event['weather_condition']}, Speed: {event.get('current_speed_kmh')} km/h). Running ML logistics evaluation...")
        
    # Fetch GraphDB context
    context = query_graphdb_context(delivery_id)
    if not context:
        print(f"    [-] Error: Could not resolve GraphDB context for {delivery_id}. Skipping.")
        return
        
    if debug:
        print(f"    [DEBUG] GraphDB Context: Lead Time Days={context['lead_time_days']}, Supplier Reliability={context['supplier_reliability_score']:.2f}")

    # Build Feature Vector matching the 26 features exactly
    input_dict = {feat: np.nan for feat in feature_names}
    
    # Fill in known telemetry features
    input_dict["vehicle_gps_latitude"] = event["gps_location"]["lat"]
    input_dict["vehicle_gps_longitude"] = event["gps_location"]["lon"]
    input_dict["iot_temperature"] = float(event.get("cargo_temp_celsius", np.nan))
    input_dict["disruption_likelihood_score"] = float(event.get("disruption_probability", np.nan))
    
    # Map weather string to severity scalar
    weather_map = {"Clear": 0.1, "Windy": 0.3, "Light Rain": 0.4, "Heavy Snow": 0.7, "Storm": 0.9}
    input_dict["weather_condition_severity"] = weather_map.get(event["weather_condition"], 0.2)
    
    # Map speed to congestion level
    speed = event.get("current_speed_kmh", 80.0)
    input_dict["traffic_congestion_level"] = 6.0 if speed == 0.0 else 1.0

    # Fill in GraphDB context features
    input_dict["lead_time_days"] = context["lead_time_days"]
    input_dict["supplier_reliability_score"] = context["supplier_reliability_score"]
    
    # Parse timestamp features
    ts = pd.to_datetime(event["discovery_timestamp"])
    input_dict["month"] = ts.month
    input_dict["day"] = ts.day
    input_dict["hour"] = ts.hour
    input_dict["dayofweek"] = ts.dayofweek

    # Convert to DataFrame with single row
    X_input = pd.DataFrame([input_dict], columns=feature_names)
    
    # Run Inference (imputes missing values automatically via median imputer in pipeline)
    predicted_delay = pipeline.predict(X_input)[0]
    print(f"    [i] ML Model Predicted Transit Delay Deviation: {predicted_delay:.4f} hours")
    
    # Trigger alert if prediction exceeds threshold (e.g. 0.5 hours delay)
    if predicted_delay > 0.5:
        # Round delay hours to integer for backend schema
        estimated_delay_hours = int(round(max(1.0, predicted_delay)))
        disruption_prob = float(event.get("disruption_probability", min(1.0, predicted_delay / 10.0)))
        
        # Reason code mapping based on weather
        weather = event.get("weather_condition", "Clear")
        reason = "Transport/Weather" if weather in ["Storm", "Heavy Snow", "Windy"] else "Carrier_Issue"
        
        print(f"    [!] RISK FLAGGED! Predicted Delay: {predicted_delay:.2f}h. Invoking API...")
        
        payload = {
            "delivery_id": delivery_id,
            "estimated_delay_hours": estimated_delay_hours,
            "reason_code": reason,
            "disruption_probability": disruption_prob,
            "timestamp": event["discovery_timestamp"]
        }
        
        try:
            res = requests.post(BACKEND_URL, json=payload, timeout=60)
            if res.status_code == 200:
                print(f"    [+] API Success: Alarm generated securely.")
                alert_text = res.json().get("alert_text", "None")
                print("    [+] Alert text:", alert_text)
            else:
                print(f"    [!] API Warning: Backend returned status code {res.status_code}")
                print(res.text)
        except Exception as err:
            print(f"    [!] API Error: Could not connect to backend server: {err}")
    else:
        print("    [+] Shipment is on track or delay is negligible. No alert triggered.")

def run_simulation():
    """Runs the stream simulation using telemetry_stream_logistics.json."""
    print("\n" + "=" * 60)
    print("  RUNNING LOGISTICS STREAM INGESTION SIMULATION")
    print("=" * 60)
    
    if not os.path.exists(TELEMETRY_STREAM_PATH):
        raise FileNotFoundError(f"Telemetry stream file missing at: {TELEMETRY_STREAM_PATH}")
        
    pipeline, feature_names = load_logistics_assets()
    print(f"[*] Successfully loaded Linear Regression pipeline model.")
    print(f"[*] Model expects {len(feature_names)} features.")
    
    with open(TELEMETRY_STREAM_PATH, "r") as f:
        events = json.load(f)
        
    print(f"[*] Processing {len(events)} telemetry events...")
    for event in events:
        execute_stream_prediction(event, pipeline, feature_names)
        
    print("\n" + "=" * 60)
    print("  SIMULATION INGESTION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    run_simulation()
