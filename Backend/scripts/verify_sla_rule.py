"""
verify_sla_rule.py

Standalone, LLM-independent test of the new reason-code SLA rule
(_apply_reason_code_sla_rule). The live /simulate-iot endpoint can't
currently demonstrate this rule because the OpenRouter LLM call is
failing (402 - no credits) BEFORE risk classification ever happens,
so the exception fallback (risks=["DelayEvent"]) always wins
regardless of reason_code. This script calls the rule function
directly, simulating what the LLM *would* have proposed, to prove
the rule's logic is correct independent of the LLM being reachable.

Run from the Backend folder:
    python verify_sla_rule.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.risk_engine_service import _apply_reason_code_sla_rule

print("=" * 70)
print("Testing _apply_reason_code_sla_rule() directly (LLM-independent)")
print("=" * 70)

# Each case simulates what the LLM might have proposed as risks,
# before our deterministic rule is applied on top.
test_cases = [
    (["DelayEvent", "SLAViolation"], "Carrier_Issue", True, "Carrier fault -> SHOULD be SLA violation"),
    (["DelayEvent", "SLAViolation"], "CustomsDelay", True, "Customs hold -> SHOULD be SLA violation"),
    (["DelayEvent", "SLAViolation"], "Customs_Hold", True, "Customs hold (alt spelling) -> SHOULD be SLA violation"),
    (["DelayEvent", "SLAViolation"], "Transport/Weather", False, "Weather -> should NOT be SLA violation"),
    (["DelayEvent", "SLAViolation"], "Weather_Delay", False, "Weather (alt) -> should NOT be SLA violation"),
    (["DelayEvent", "SLAViolation"], "Port_Congestion", False, "Port congestion -> should NOT be SLA violation"),
    (["DelayEvent"], "Transport/Weather", False, "No SLAViolation proposed -> stays absent either way"),
]

all_passed = True
for risks_in, reason, expected_sla, description in test_cases:
    result = _apply_reason_code_sla_rule(list(risks_in), reason)
    has_sla = "SLAViolation" in result
    passed = has_sla == expected_sla
    all_passed = all_passed and passed
    status = "PASS" if passed else "FAIL"
    print(f"\n[{status}] {description}")
    print(f"        Input risks:  {risks_in}, reason_code: {reason!r}")
    print(f"        Output risks: {result}")
    print(f"        SLAViolation present: {has_sla} (expected: {expected_sla})")

print()
print("=" * 70)
if all_passed:
    print("ALL TESTS PASSED — the reason-code SLA rule is working correctly.")
    print("(The live API can't show this right now only because the LLM call")
    print(" fails first due to OpenRouter credits, not because the rule is broken.)")
else:
    print("SOME TESTS FAILED — see details above.")
print("=" * 70)
