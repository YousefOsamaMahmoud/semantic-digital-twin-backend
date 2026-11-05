from services.dashboard_service import get_risk_scores, get_compliance_alerts

print("=== RELIABILITY SCORES ===")
scores = get_risk_scores()
for s in scores:
    print(f"  {s['supplier']:30s} | score={s['reliabilityScore']} | status={s['status']}")

print()
print("=== COMPLIANCE ALERTS (for penalty calc) ===")
alerts = get_compliance_alerts()
for a in alerts:
    print(f"  {a['supplier']:30s} | delay={a['delayDays']}d | rate={a['penaltyRate']} | compliance={a['compliance']}% | violation={a['violationStatus']}")
