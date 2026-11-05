# =====================================================================
# Machine_Learning/New dataset/seed_evaluation_context.py
#
# Seeding script to ground our stream simulation in unseen test data.
# This script:
#   1. Loads the 20% unseen evaluation shipments from evaluation_shipments.xlsx.
#   2. Picks three representative test shipments (nominal, medium delay, severe delay).
#   3. Generates mock deliveries (DEL_EVAL_001, etc.) and suppliers.
#   4. Seeds their static contract properties (leadTimeDays, hasReliabilityScore)
#      directly in Ontotext GraphDB.
#   5. Seeds inventory & processes so that delayed shipments trigger 
#      ProductionDisruption reasoning alerts in the risk engine.
#   6. Generates a matching telemetry stream log telemetry_stream_logistics.json.
# =====================================================================

import os
import sys
import json
import numpy as np
import pandas as pd

# Allow importing backend modules by adding the Backend folder to Python Path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BACKEND_PATH = os.path.join(PROJECT_ROOT, "Backend")
sys.path.append(BACKEND_PATH)

from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES, CONTRACT_GRAPH

EVAL_DATASET_PATH = os.path.join(SCRIPT_DIR, "evaluation_shipments.xlsx")
TELEMETRY_EXPORT_PATH = os.path.join(PROJECT_ROOT, "Data_Science", "data_Lake", "iot_streams", "telemetry_stream_logistics.json")

def seed_graphdb_and_generate_telemetry():
    print("=" * 60)
    print("  SEEDING GRAPHDB WITH EVALUATION SET SHIPPINGS")
    print("=" * 60)

    if not os.path.exists(EVAL_DATASET_PATH):
        raise FileNotFoundError(f"Evaluation dataset missing at: {EVAL_DATASET_PATH}")

    df = pd.read_excel(EVAL_DATASET_PATH)

    # Sort to find three clear profiles:
    # 1. Nominal shipment (predicted deviation <= 0)
    # 2. Medium delay shipment (predicted deviation between 2 and 5)
    # 3. Severe delay shipment (predicted deviation > 7)
    df_sorted = df.sort_values(by="delivery_time_deviation")
    
    nominal_row = df_sorted[df_sorted["delivery_time_deviation"] <= 0].iloc[0]
    med_row = df_sorted[(df_sorted["delivery_time_deviation"] > 2) & (df_sorted["delivery_time_deviation"] < 5)].iloc[0]
    severe_row = df_sorted[df_sorted["delivery_time_deviation"] >= 7].iloc[-1]

    selected_rows = [
        ("DEL_EVAL_001", nominal_row),
        ("DEL_EVAL_002", med_row),
        ("DEL_EVAL_003", severe_row)
    ]

    triples = []
    telemetry_events = []

    # Seeding inventory variables to ensure stock falls below safety levels
    # when delayed, triggering ProductionDisruption reasoning in the ontology.
    for i, (del_id, row) in enumerate(selected_rows, 1):
        sup_uri = f"Supplier_EVAL_{i:03d}"
        sup_label = f"Evaluation Supplier {i:03d}"
        mat_uri = f"Material_EVAL_{i:03d}"
        mat_label = f"Raw Chemical EVAL_{i:03d}"
        proc_uri = f"Process_EVAL_{i:03d}"
        proc_label = f"Assembly Line EVAL_{i:03d}"

        lead_days = int(row["lead_time_days"])
        rel_score = float(row["supplier_reliability_score"])

        print(f"[*] Shipment {del_id} details:")
        print(f"    - Supplier Reliability: {rel_score:.2f}")
        print(f"    - Lead Time Days: {lead_days}")
        print(f"    - Expected Target Delay Deviation: {row['delivery_time_deviation']:.4f} hours")

        # Create RDF Triples
        triples.append(f"""
            # Supplier
            :{sup_uri} rdf:type :Supplier ;
                      rdfs:label "{sup_label}" ;
                      :hasReliabilityScore "{rel_score}"^^xsd:float .

            # Material & supplies relationship
            :{mat_uri} rdf:type :RawMaterial ;
                      rdfs:label "{mat_label}" ;
                      :isSuppliedBy :{sup_uri} ;
                      :hasInventoryStock 60 ;
                      :hasSafetyStockLevel 100 ;
                      :affectsProcess :{proc_uri} .

            # Production process
            :{proc_uri} rdf:type :ProductionProcess ;
                       rdfs:label "{proc_label}" .

            # Delivery Event
            :{del_id} rdf:type :DeliveryEvent ;
                      :transports :{mat_uri} ;
                      :poType "Standard" ;
                      :supplierRegion "EU" ;
                      :paymentTerms "Net 30" ;
                      :unitOfMeasure "LITERS" ;
                      :hasUnitCost 12.50 ;
                      :discountPct 0.0 ;
                      :taxPct 10.0 ;
                      :lineNet 1250.00 ;
                      :hasCurrency "EUR" ;
                      :savingsPct 5.0 ;
                      :leadTimeDays {lead_days} ;
                      :department "Operations" ;
                      :contractType "Master Supply" ;
                      :maverickSpend "No" ;
                      :singleSourceFlag "No" ;
                      :preferredSupplier "Yes" ;
                      :localInternational "Local" .
        """)

        # Determine weather string from severity
        severity = row["weather_condition_severity"]
        if severity >= 0.8:
            weather = "Storm"
        elif severity >= 0.6:
            weather = "Heavy Snow"
        elif severity >= 0.3:
            weather = "Windy"
        else:
            weather = "Clear"

        # Determine speed from congestion
        congestion = row["traffic_congestion_level"]
        if congestion >= 5.0:
            speed = 0.0
        else:
            speed = 80.0

        # Construct Telemetry Stream Events
        # We will create two telemetry events per delivery (one nominal/scheduled, one in-transit anomaly)
        timestamp_base = f"2026-03-{10+i:02d}"
        
        # Event 1: Scheduled/Nominal
        telemetry_events.append({
            "discovery_timestamp": f"{timestamp_base}T10:00:00Z",
            "delivery_id": del_id,
            "route_id": f"Route_EVAL_{i:03d}",
            "carrier_3pl": f"3PL_EVAL_{i:03d}",
            "gps_location": {"lat": 48.8566, "lon": 2.3522},
            "current_speed_kmh": 80.0,
            "cargo_temp_celsius": float(row["iot_temperature"]),
            "status_code": "Scheduled",
            "weather_condition": "Clear",
            "risk_status": "None"
        })

        # Event 2: In-Transit Anomaly (triggers prediction)
        telemetry_events.append({
            "discovery_timestamp": f"{timestamp_base}T14:30:00Z",
            "delivery_id": del_id,
            "route_id": f"Route_EVAL_{i:03d}",
            "carrier_3pl": f"3PL_EVAL_{i:03d}",
            "gps_location": {
                "lat": float(row["vehicle_gps_latitude"]), 
                "lon": float(row["vehicle_gps_longitude"])
            },
            "current_speed_kmh": speed,
            "cargo_temp_celsius": float(row["iot_temperature"]),
            "status_code": "Shipped",
            "weather_condition": weather,
            "risk_status": "Potential",
            "disruption_probability": float(row["disruption_likelihood_score"])
        })

    # Combine triples into SPARQL update query
    sparql_update = f"""{PREFIXES}
    INSERT DATA {{
        GRAPH <{CONTRACT_GRAPH}> {{
            {" ".join(triples)}
        }}
    }}
    """

    print("[*] Executing SPARQL update on GraphDB...")
    try:
        graphdb.execute_sparql_update(sparql_update)
        print("[+] GraphDB successfully seeded with evaluation shippings context.")
    except Exception as exc:
        print(f"[!] Error seeding GraphDB: {exc}")
        print("[!] Make sure GraphDB is running on port 7200 and the repository SemanticDigitalTwin is active.")
        sys.exit(1)

    print(f"[*] Exporting telemetry stream log to: {TELEMETRY_EXPORT_PATH}...")
    os.makedirs(os.path.dirname(TELEMETRY_EXPORT_PATH), exist_ok=True)
    with open(TELEMETRY_EXPORT_PATH, "w") as f:
        json.dump(telemetry_events, f, indent=2)

    print("[+] Seeding and telemetry stream creation complete.")
    return True

if __name__ == "__main__":
    seed_graphdb_and_generate_telemetry()
