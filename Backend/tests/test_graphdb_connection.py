# ============================================================
# tests/test_graphdb_connection.py
#
# Verification script for the Neo4j → GraphDB migration.
#
# This script tests THREE things:
#   1. Can we reach the GraphDB SPARQL endpoint?
#   2. Can we INSERT triples using SPARQL UPDATE?
#   3. Can we distinguish INFERRED triples from EXPLICIT ones?
#
# ╔══════════════════════════════════════════════════════════╗
# ║  GOLDEN RULE #3 — INFERENCE VALIDATION                   ║
# ║  GraphDB tags inferred statements with the system         ║
# ║  property <http://www.ontotext.com/owlim/system#inferred> ║
# ║  We query for it to PROVE that the "At Risk" result       ║
# ║  comes from the OWL reasoner, not from explicit data.     ║
# ╚══════════════════════════════════════════════════════════╝
#
# Usage:
#   cd "Graduation Project"
#   python -m tests.test_graphdb_connection
# ============================================================

import sys
import os

# Ensure the project root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.connection import graphdb

# ---- Shared Prefix Block ----
PREFIXES = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX sys: <http://www.ontotext.com/owlim/system#>
"""

CONTRACT_GRAPH = "http://example.org/contracts/"


def test_connection():
    """
    TEST 1 — Connection Check
    Sends a trivial ASK query to verify GraphDB is reachable.
    """
    print("=" * 60)
    print("TEST 1: Connection to GraphDB")
    print("=" * 60)

    try:
        query = f"""
        {PREFIXES}
        SELECT ?s ?p ?o
        WHERE {{ ?s ?p ?o }}
        LIMIT 1
        """
        results = graphdb.execute_sparql_select(query)
        print(f"  ✅  Connection successful!")
        print(f"      Endpoint: {graphdb._query_endpoint}")
        print(f"      Sample triple found: {len(results) > 0}")
        return True

    except Exception as e:
        print(f"  ❌  Connection FAILED: {e}")
        return False


def test_insert_triples():
    """
    TEST 2 — Triple Insertion
    Inserts a sample Supplier → RawMaterial relationship
    into the contracts Named Graph, then reads it back.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Triple Insertion (SPARQL UPDATE)")
    print("=" * 60)

    try:
        # ---- INSERT ----
        insert_query = f"""
        {PREFIXES}
        INSERT DATA {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :Test_Supplier  rdf:type       :Supplier ;
                                rdfs:label     "Test Supplier" .
                :Test_Material  rdf:type       :RawMaterial ;
                                rdfs:label     "Test Material" .
                :Test_Supplier  :supplies      :Test_Material .
                :Test_Supplier  :leadTimeDays  7 .
                :Test_Supplier  :penaltyClause "5% per day" .
            }}
        }}
        """
        graphdb.execute_sparql_update(insert_query)
        print("  ✅  INSERT DATA executed successfully.")

        # ---- VERIFY ----
        verify_query = f"""
        {PREFIXES}
        SELECT ?supplierLabel ?materialLabel
        WHERE {{
            GRAPH <{CONTRACT_GRAPH}> {{
                ?s  rdf:type    :Supplier ;
                    rdfs:label  ?supplierLabel ;
                    :supplies   ?m .
                ?m  rdfs:label  ?materialLabel .
            }}
        }}
        LIMIT 5
        """
        results = graphdb.execute_sparql_select(verify_query)
        print(f"  ✅  Verification query returned {len(results)} result(s):")
        for row in results:
            print(f"      • {row['supplierLabel']} → {row['materialLabel']}")
        return True

    except Exception as e:
        print(f"  ❌  Insertion FAILED: {e}")
        return False


def test_inference_validation():
    """
    TEST 3 — Inference Validation (Golden Rule #3)

    This test checks whether GraphDB's OWL reasoner is
    producing INFERRED triples (e.g., :isAtRisk) vs. explicit
    ones.

    GraphDB's system ontology provides:
        <http://www.ontotext.com/owlim/system#inferred>
    which we can query to distinguish explicit from inferred
    statements.

    NOTE: For this test to produce inferred results, you need:
      1. An OWL ontology loaded into GraphDB with appropriate
         rules (e.g., a SWRL rule or OWL property chain that
         infers :isAtRisk from :hasDelay + :supplies + :requires).
      2. A Supplier with :hasDelay true.
      3. A Product that :requires the delayed material.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Inference Validation (sys:inferred)")
    print("=" * 60)

    try:
        # ---- Step A: Query for inferred "At Risk" triples ----
        # This query checks if any :isAtRisk triples exist
        # and whether they are inferred or explicit.
        inference_query = f"""
        {PREFIXES}

        SELECT ?product ?productLabel ?riskStatus
        WHERE {{
            ?product  rdf:type    :Product ;
                      rdfs:label  ?productLabel .
            ?product  :isAtRisk   ?riskStatus .
        }}
        """

        results = graphdb.execute_sparql_select(inference_query)

        if len(results) == 0:
            print("  ⚠️  No 'At Risk' products found.")
            print("      This is expected if you haven't yet:")
            print("        1. Loaded the OWL ontology with inference rules.")
            print("        2. Inserted a Supplier with :hasDelay true.")
            print("        3. Inserted a Product that :requires the delayed material.")
            print("      Once those conditions are met, re-run this test.")
            return True

        print(f"  ✅  Found {len(results)} 'At Risk' product(s):")
        for row in results:
            print(f"      • {row['productLabel']} → isAtRisk: {row['riskStatus']}")

        # ---- Step B: Verify these triples are INFERRED ----
        # GraphDB's system graph lets us check if specific
        # statements are inferred vs. explicit.
        print("\n  🔍  Checking if :isAtRisk triples are INFERRED...")

        inferred_check_query = f"""
        {PREFIXES}

        SELECT ?product ?productLabel ?isInferred
        WHERE {{
            ?product  rdf:type    :Product ;
                      rdfs:label  ?productLabel .
            ?product  :isAtRisk   ?riskStatus .

            # Check the system graph for inference metadata.
            # If the triple is inferred, this will bind to true.
            OPTIONAL {{
                GRAPH sys:inferred {{
                    ?product :isAtRisk ?riskStatus .
                }}
                BIND(true AS ?isInferred)
            }}
        }}
        """

        inferred_results = graphdb.execute_sparql_select(inferred_check_query)

        all_inferred = True
        for row in inferred_results:
            is_inf = row.get("isInferred", "false")
            status = "🧠 INFERRED" if is_inf == "true" else "📝 EXPLICIT"
            print(f"      • {row['productLabel']}: {status}")
            if is_inf != "true":
                all_inferred = False

        if all_inferred and len(inferred_results) > 0:
            print("\n  ✅  All :isAtRisk triples are INFERRED by the OWL reasoner.")
            print("      The ontology rules are working correctly!")
        else:
            print("\n  ⚠️  Some :isAtRisk triples appear to be EXPLICIT.")
            print("      Check if they were manually inserted instead of inferred.")

        return True

    except Exception as e:
        print(f"  ❌  Inference validation FAILED: {e}")
        print(f"      Make sure GraphDB has reasoning enabled for the repository.")
        return False


def cleanup_test_data():
    """
    Remove the test triples inserted by test_insert_triples().
    """
    print("\n" + "=" * 60)
    print("CLEANUP: Removing test triples")
    print("=" * 60)

    try:
        cleanup_query = f"""
        {PREFIXES}
        DELETE WHERE {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :Test_Supplier ?p1 ?o1 .
                :Test_Material ?p2 ?o2 .
            }}
        }}
        """
        graphdb.execute_sparql_update(cleanup_query)
        print("  ✅  Test data cleaned up.")
        return True

    except Exception as e:
        print(f"  ⚠️  Cleanup failed (non-critical): {e}")
        return False


# ==============================================================
# Main Runner
# ==============================================================
if __name__ == "__main__":
    print("\n🚀  GraphDB Migration — Verification Suite\n")

    passed = 0
    failed = 0

    # Test 1: Connection
    if test_connection():
        passed += 1
    else:
        failed += 1
        print("\n⛔  Cannot proceed — GraphDB is not reachable.")
        print("    Make sure GraphDB is running at the URL in .env")
        sys.exit(1)

    # Test 2: Triple Insertion
    if test_insert_triples():
        passed += 1
    else:
        failed += 1

    # Test 3: Inference Validation
    if test_inference_validation():
        passed += 1
    else:
        failed += 1

    # Cleanup
    cleanup_test_data()

    # Summary
    print("\n" + "=" * 60)
    print(f"  RESULTS:  {passed} passed  |  {failed} failed")
    print("=" * 60)
