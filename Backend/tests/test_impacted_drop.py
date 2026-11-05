from services.dashboard_service import find_impacted_products_by_supplier_delay, get_risk_scores

impacted = find_impacted_products_by_supplier_delay()
print("IMPACTED:", impacted)
scores = get_risk_scores()
print("SCORES:", [s for s in scores if s['status'] == 'RED'])
