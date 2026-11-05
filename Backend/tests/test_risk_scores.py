import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.dashboard_service import get_risk_scores

try:
    scores = get_risk_scores()
    print(f"Total scores: {len(scores)}")
    
    # Check for duplicates by material substring
    # Let's print out all materials just to see what's in there.
    for s in scores:
        print(f"Supplier: {s['supplier']} | Material: {s['material']} | Process: {s['process']}")

except Exception as e:
    import traceback
    traceback.print_exc()
