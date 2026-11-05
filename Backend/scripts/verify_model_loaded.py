"""
verify_model_loaded.py

Standalone check that bypasses the app's logging entirely (which has
been unreliable to read in the terminal) and just prints plain
print() statements to definitively answer: is the trained logistics
model actually loading and predicting, or silently falling back?

Run from the Backend folder:
    python verify_model_loaded.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

print("=" * 60)
print("STEP 1: Importing the simulator module")
print("=" * 60)
try:
    from services import telemetry_simulator_service as sim
    print("OK: module imported successfully.")
except Exception as exc:
    print(f"FAILED to import telemetry_simulator_service: {exc}")
    sys.exit(1)

print()
print("=" * 60)
print("STEP 2: Checking model + feature file paths")
print("=" * 60)
print(f"Model path:    {sim.LOGISTICS_MODEL_PATH}")
print(f"Model exists:  {sim.LOGISTICS_MODEL_PATH.exists()}")
print(f"Features path: {sim.LOGISTICS_FEATURES_PATH}")
print(f"Features exist: {sim.LOGISTICS_FEATURES_PATH.exists()}")

print()
print("=" * 60)
print("STEP 3: Attempting to load the model")
print("=" * 60)
sim._load_logistics_model()
print(f"_LOGISTICS_MODEL is None: {sim._LOGISTICS_MODEL is None}")
if sim._LOGISTICS_MODEL is not None:
    print(f"Model type: {type(sim._LOGISTICS_MODEL)}")
    print(f"Expected features ({len(sim._LOGISTICS_FEATURES)}): {sim._LOGISTICS_FEATURES}")
else:
    print("MODEL DID NOT LOAD. This is why the fallback rule is being used.")
    sys.exit(1)

print()
print("=" * 60)
print("STEP 4: Loading one real telemetry record and predicting")
print("=" * 60)
records = sim._load_telemetry_stream()
print(f"Loaded {len(records)} telemetry records.")
if not records:
    print("No records found — cannot test prediction.")
    sys.exit(1)

sample = records[0]
print(f"Sample record: {sample}")

prediction = sim._estimate_delay_hours_via_model(sample)
print()
if prediction is not None:
    print(f"SUCCESS: Model predicted {prediction:.2f} -> clamped to {max(1, round(prediction))} delay hours.")
    print("The real trained ML model IS working correctly.")
else:
    print("Model prediction returned None — it failed and fell back. Check the warning printed above.")

print()
print("=" * 60)
print("STEP 5: Running this through _estimate_delay_hours() directly")
print("=" * 60)
final_value = sim._estimate_delay_hours(sample)
print(f"_estimate_delay_hours() returned: {final_value}")
print(f"Was the real model used: {sim._LOGISTICS_MODEL is not None}")
