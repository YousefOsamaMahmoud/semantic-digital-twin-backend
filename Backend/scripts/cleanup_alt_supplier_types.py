"""
cleanup_alt_supplier_types.py
─────────────────────────────
Removes the spurious rdf:type :Supplier that assign_fallback_supplier()
previously inserted onto AlternativeSupplier nodes (Wayne Electronics Ltd.
and NovaPower Energy Ltd.).  Those nodes should ONLY carry the type
:AlternativeSupplier so they do not contaminate get_risk_scores() queries.
"""
from knowledge_base.connection import graphdb

PREFIX = "PREFIX : <http://example.org/ontology#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>"

# ── 1. Show current state ────────────────────────────────────────────────────
print("Before cleanup – nodes typed as BOTH :Supplier AND :AlternativeSupplier:")
check_q = f"""
{PREFIX}
SELECT ?s ?label WHERE {{
    ?s rdf:type :Supplier ;
       rdf:type :AlternativeSupplier .
    OPTIONAL {{ ?s rdfs:label ?label . }}
}}
"""
rows = graphdb.execute_sparql_select(check_q)
if not rows:
    print("  (none — already clean)")
else:
    for r in rows:
        print(f"  {r.get('label', r.get('s', '?'))}")

# ── 2. Remove the polluted :Supplier type from every :AlternativeSupplier ────
cleanup_q = f"""
{PREFIX}
DELETE {{
    GRAPH ?g {{ ?s rdf:type :Supplier . }}
}}
WHERE {{
    GRAPH ?g {{
        ?s rdf:type :Supplier ;
           rdf:type :AlternativeSupplier .
    }}
}}
"""
try:
    graphdb.execute_sparql_update(cleanup_q)
    print("\nCleanup query executed successfully.")
except Exception as e:
    print(f"\nCleanup failed: {e}")

# ── 3. Confirm result ────────────────────────────────────────────────────────
print("\nAfter cleanup – nodes typed as BOTH (should be empty):")
rows_after = graphdb.execute_sparql_select(check_q)
if not rows_after:
    print("  (none — clean!)")
else:
    for r in rows_after:
        print(f"  {r.get('label', r.get('s', '?'))}")
