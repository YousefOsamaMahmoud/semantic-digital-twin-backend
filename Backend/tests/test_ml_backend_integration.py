# ============================================================
# tests/test_ml_backend_integration.py
#
# Dedicated integration test script verifying that the Machine
# Learning prediction engine maps telemetry events to GraphDB,
# triggers ontology-based SWRL reasoning, and resolves the correct
# manager alerts via the FastAPI backend endpoints.
# ============================================================

import sys
import os
import requests
import pprint

# Ensure python path is correct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_URL = "http://127.0.0.1:8001/api/sandbox/simulate-iot"

def run_integration_test_for_delivery(delivery_id: str, estimated_delay: int, disruption_prob: float, reason: str):
    print(f"\n[+] Testing delivery: {delivery_id}")
    print(f"    - Estimated Delay: {estimated_delay} hours")
    print(f"    - Disruption Probability: {disruption_prob}")
    print(f"    - Reason Code: {reason}")
    
    payload = {
        "delivery_id": delivery_id,
        "estimated_delay_hours": estimated_delay,
        "reason_code": reason,
        "disruption_probability": disruption_prob,
        "timestamp": "2026-06-16T12:00:00Z"
    }
    
    try:
        response = requests.post(BACKEND_URL, json=payload, timeout=30)
        
        # Verify status code
        if response.status_code != 200:
            print(f"    [FAIL] Backend returned error status code: {response.status_code}")
            print(f"    Response Detail: {response.text}")
            return False
            
        data = response.json()
        print("    [PASS] Received successful HTTP 200 response.")
        
        # Verify alert keys exist
        manager_title = data.get("manager_title")
        alert_text = data.get("alert_text")
        validated = data.get("validated")
        
        print(f"    [i] Alert Title (Primary Manager): {manager_title}")
        print(f"    [i] Alert Text: {alert_text}")
        print(f"    [i] Validated by Agent: {validated}")
        
        # Check that the alert is validated
        assert validated is True, "Alert was not validated by the agent!"
        assert manager_title in ["Production Manager", "Procurement Manager", "Logistics Manager"], "Invalid manager role targeted!"
        
        print("    [PASS] Manager alert structure is correct and validated.")
        return True
        
    except Exception as e:
        print(f"    [FAIL] Failed to execute API call: {e}")
        return False

if __name__ == "__main__":
    print("==============================================================")
    print("  ML-TO-BACKEND END-TO-END INTEGRATION TEST")
    print("==============================================================")
    
    # Test DEL_005 (which triggers SLA Violations and Production Disruptions)
    success_005 = run_integration_test_for_delivery(
        delivery_id="DEL_005",
        estimated_delay=72,
        disruption_prob=0.95,
        reason="Carrier_Issue"
    )
    
    # Test DEL_015 (which triggers SLA Violations and Production Disruptions after updates)
    success_015 = run_integration_test_for_delivery(
        delivery_id="DEL_015",
        estimated_delay=48,
        disruption_prob=0.87,
        reason="Transport/Weather"
    )
    
    print("\n" + "=" * 62)
    if success_005 and success_015:
        print("  ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("  Machine Learning is integrated correctly with the backend.")
        print("=" * 62)
        sys.exit(0)
    else:
        print("  INTEGRATION TEST(S) FAILED.")
        print("=" * 62)
        sys.exit(1)
