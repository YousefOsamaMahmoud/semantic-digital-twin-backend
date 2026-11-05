import sys
import os
import requests
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES

def get_reliability_score(supplier_id):
    query = f"""{PREFIXES}
    SELECT ?score
    WHERE {{
        :{supplier_id} :hasReliabilityScore ?score .
    }}
    """
    res = graphdb.execute_sparql_select(query)
    if res:
        return float(res[0]["score"])
    return None

def test_flow():
    print("=" * 60)
    print("  TESTING EVENT-DRIVEN SUPPLIER SCORE UPDATES (OPTION 3)")
    print("=" * 60)
    
    # 1. Reset baseline score for VoltSupply_Global to 0.85
    print("[1] Resetting baseline score for VoltSupply_Global to 0.85...")
    
    # Reset VoltSupply_Global score to 0.85 first to ensure standard starting point
    graphdb.execute_sparql_update(f"""{PREFIXES}
        DELETE WHERE {{ :VoltSupply_Global :hasReliabilityScore ?o }}
    """)
    graphdb.execute_sparql_update(f"""{PREFIXES}
        INSERT DATA {{ :VoltSupply_Global :hasReliabilityScore 0.85 }}
    """)
    
    score_initial = get_reliability_score("VoltSupply_Global")
    print(f"    - Initial Score for VoltSupply_Global: {score_initial}")
    
    # 2. Place a new order
    print("\n[2] Placing a new Purchase Order...")
    url_place = "http://localhost:8001/api/sandbox/place-order"
    payload_place = {
        "supplier_id": "VoltSupply_Global",
        "material_id": "Lithium_Ion_Battery_Pack",
        "quantity": 1000,
        "unit_price": 150.0,
        "po_date": "2026-03-05",
        "po_type": "Standard",
        "department": "Operations"
    }
    res_place = requests.post(url_place, json=payload_place)
    if res_place.status_code != 200:
        print("    [FAIL] Failed to place order:", res_place.text)
        return
        
    data_place = res_place.json()
    delivery_id = data_place["delivery_id"]
    print(f"    - Successfully placed order. Generated Delivery ID: {delivery_id}")
    
    score_after_place = get_reliability_score("VoltSupply_Global")
    print(f"    - Score for VoltSupply_Global after placing PO: {score_after_place}")
    
    # 3. Simulate an IoT delay for this specific Delivery ID
    print(f"\n[3] Simulating IoT Telemetry Delay for {delivery_id}...")
    url_iot = "http://localhost:8001/api/sandbox/simulate-iot"
    payload_iot = {
        "timestamp": "2026-03-05T15:30:00Z",
        "delivery_id": delivery_id,
        "reason_code": "Weather_Delay",
        "disruption_probability": 0.95,
        "estimated_delay_hours": 96  # Heavy 4-day delay
    }
    res_iot = requests.post(url_iot, json=payload_iot)
    if res_iot.status_code != 200:
        print("    [FAIL] Failed to simulate IoT:", res_iot.text)
        return
        
    print("    - IoT event simulated successfully.")
    
    # Wait a moment for background thread score update to finish
    print("    - Waiting 10 seconds for background recalculation to complete...")
    time.sleep(10)
    
    score_after_delay = get_reliability_score("VoltSupply_Global")
    print(f"    - Score for VoltSupply_Global after 96h Delay: {score_after_delay}")
    
    print("\n" + "=" * 60)
    if score_after_delay is not None and score_after_delay < score_after_place:
        print("  [PASS] AUTOMATIC EVENT-DRIVEN RELIABILITY UPDATES SUCCESSFUL!")
    else:
        print("  [FAIL] Supplier score was not penalized by delay.")
    print("=" * 60)

if __name__ == "__main__":
    test_flow()
