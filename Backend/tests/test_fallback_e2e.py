import sys, io
sys.path.append(".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from services.dashboard_service import get_fallback_options, get_risk_scores
from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES

# ── 1. Check what types are stored for all suppliers in GraphDB ──────────────
print("=" * 60)
print("1. ALL SUPPLIER TYPES IN GRAPHDB")
print("=" * 60)
type_query = f"""
{PREFIXES}
SELECT ?supplierLabel ?type WHERE {{
    ?s rdf:type ?type .
    FILTER(?type IN (:Supplier, :AlternativeSupplier))
    OPTIONAL {{ ?s rdfs:label ?supplierLabel . }}
}}
ORDER BY ?type ?supplierLabel
"""
rows = graphdb.execute_sparql_select(type_query)
for r in rows:
    print(f"  [{r.get('type','?').split('#')[-1]:25s}]  {r.get('supplierLabel','(no label)')}")

# ── 2. Test get_risk_scores — what shows as RED ───────────────────────────────
print()
print("=" * 60)
print("2. RISK SCORES (should only show primary Suppliers as RED)")
print("=" * 60)
scores = get_risk_scores()
for s in scores:
    print(f"  [{s['status']}]  supplier={s.get('supplier','?')!r:35s}  material={s.get('material','?')!r}")

# ── 3. Test fallback options for each at-risk material ───────────────────────
print()
print("=" * 60)
print("3. FALLBACK OPTIONS PER MATERIAL (should be ONLY alternatives)")
print("=" * 60)
materials = ["Micro-Controllers (MCU)", "Lithium Battery Cells", "Carbon Fiber Sheets", "Semiconductor Wafers"]
for m in materials:
    results = get_fallback_options(m)
    print(f"\n  Material: {m!r}  ->  {len(results)} option(s) returned")
    for i, r in enumerate(results):
        print(f"    #{i+1}  name={r.get('supplierName','?')!r:30s}  score={r.get('reliabilityScore','?')}")
