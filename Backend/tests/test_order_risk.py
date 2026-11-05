# =====================================================================
# Backend/tests/test_order_risk.py
#
# Integration test verifying the Procurement Order Planning API route.
# Checks that the endpoint resolves Ontotext GraphDB context, engineers
# features, and runs model predictions returning correct schemas.
# =====================================================================

import os
import sys
import requests
import pprint

# Allow importing backend modules by adding the Backend folder to Python Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_URL = "http://127.0.0.1:8001/api/sandbox/predict-order-risk"

def run_order_risk_test(supplier_id: str, material_id: str, quantity: int, unit_price: float, po_date: str):
    print(f"\n[+] Evaluating Proposed Purchase Order:")
    print(f"    - Supplier: {supplier_id}")
    print(f"    - Material: {material_id}")
    print(f"    - Quantity: {quantity}")
    print(f"    - Unit Price: ${unit_price:.2f}")
    print(f"    - PO Date: {po_date}")
    
    payload = {
        "supplier_id": supplier_id,
        "material_id": material_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "po_date": po_date
    }
    
    try:
        res = requests.post(BACKEND_URL, json=payload, timeout=30)
        
        if res.status_code != 200:
            print(f"    [FAIL] Backend returned error code {res.status_code}: {res.text}")
            return False
            
        data = res.json()
        print("    [PASS] Received HTTP 200 response.")
        
        on_time_prob = data.get("on_time_probability")
        risk_level = data.get("risk_level")
        est_delay = data.get("estimated_delay_hours")
        features = data.get("features_used")
        
        print(f"    [i] Predicted On-Time Confidence: {on_time_prob*100:.2f}%")
        print(f"    [i] Assigned Risk Level: {risk_level}")
        print(f"    [i] Estimated Delay Hours: {est_delay}h")
        print(f"    [i] Behind-the-Scenes Features Used:")
        for k, v in sorted(features.items()):
            print(f"        - {k}: {v}")
            
        # Assertions
        assert data.get("status") == "success", "Response status should be success"
        assert 0.0 <= on_time_prob <= 1.0, "Probability must be between 0.0 and 1.0"
        assert risk_level in ["Low", "High"], "Risk level must be Low or High"
        assert isinstance(est_delay, int), "Estimated delay hours must be an integer"
        assert isinstance(features, dict), "features_used must be a dictionary"
        assert "lead_time_days" in features, "Features must contain lead_time_days"
        assert "supplier_esg_score" in features, "Features must contain supplier_esg_score"
        
        print("    [PASS] All schema and logic validations passed successfully.")
        return True
    except Exception as e:
        print(f"    [FAIL] Request execution failed: {e}")
        return False

if __name__ == "__main__":
    print("==============================================================")
    print("  PROCUREMENT ORDER RISK ENDPOINT INTEGRATION TEST")
    print("==============================================================")
    
    # Test 1: Low-risk/Standard order with Acme Steel Corp
    test_1 = run_order_risk_test(
        supplier_id="Acme_Steel_Corp",
        material_id="Cold-Rolled_Steel",
        quantity=500,
        unit_price=6.55,
        po_date="2026-03-05"
    )
    
    # Test 2: High-risk order with Supplier_EVAL_003 (Low ESG score 0.06, long lead time)
    test_2 = run_order_risk_test(
        supplier_id="Supplier_EVAL_003",
        material_id="Material_EVAL_003",
        quantity=3000,
        unit_price=45.0,
        po_date="2026-03-05"
    )
    
    print("\n" + "=" * 62)
    if test_1 and test_2:
        print("  ALL API ENDPOINT INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 62)
        sys.exit(0)
    else:
        print("  TESTS ENCOUNTERED FAILURES.")
        print("=" * 62)
        sys.exit(1)
