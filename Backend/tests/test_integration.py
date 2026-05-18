# ============================================================
# tests/test_integration.py
#
# Integration tests for Sprint 3 & 4 deliverables.
# Tests focus on import correctness, singleton thread-safety,
# fallback generation, pipeline topology, and endpoint wiring.
#
# Usage:
#   cd "Graduation Project"
#   python -m tests.test_integration
# ============================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PASS = 0
FAIL = 0


def check(predicate: bool, label: str) -> None:
    global PASS, FAIL
    if predicate:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


# ==============================================================
# 1. MODEL IMPORT & INSTANTIATION
# ==============================================================


def test_model_imports():
    print("\n" + "=" * 60)
    print("TEST: Model imports and instantiation")
    print("=" * 60)

    from models.schemas import (
        SLAContract,
        ExtractedSLAData,
        ConfirmedSLA,
        RiskAnalysisResult,
        IoTTelemetryEvent,
        ManagerAlert,
    )

    # SLAContract
    c = SLAContract(supplier_name="S1", material="M1", lead_time_days=3, penalty_clause="5%")
    check(c.supplier_name == "S1", "SLAContract instantiation")

    # ExtractedSLAData
    e = ExtractedSLAData(
        document_id="DOC-001",
        supplier_id="SUP-1",
        supplier_name="S1",
        material="M1",
        sla_lead_time_hours=72,
        delay_penalty_rate=500.0,
        missed_item_penalty_rate=150.0,
        minimum_quality_threshold=0.98,
        quality_penalty_rate=0.15,
    )
    check(e.sla_lead_time_hours == 72, "ExtractedSLAData instantiation")

    # ConfirmedSLA
    cf = ConfirmedSLA(
        extraction_id="EXT-001",
        supplier_name="S1",
        material="M1",
        lead_time_days=3,
        penalty_clause="5%",
    )
    check(cf.extraction_id == "EXT-001", "ConfirmedSLA instantiation")
    check(cf.corrections is None, "ConfirmedSLA corrections defaults to None")

    # RiskAnalysisResult
    r = RiskAnalysisResult(
        risks=["DelayEvent"],
        confidence=0.8,
        severity="High",
        financial_penalty_estimate=5000.0,
        reasoning="Test",
    )
    check("DelayEvent" in r.risks, "RiskAnalysisResult instantiation")

    # IoTTelemetryEvent
    iot = IoTTelemetryEvent(
        delivery_id="DEL-001",
        estimated_delay_hours=48,
        reason_code="Weather",
        disruption_probability=0.7,
        timestamp="2026-05-17T12:00:00Z",
    )
    check(iot.delivery_id == "DEL-001", "IoTTelemetryEvent instantiation")

    # ManagerAlert
    a = ManagerAlert(manager_title="Production Manager", alert_text="Delivery at risk.")
    check(a.validated is False, "ManagerAlert validated defaults to False")

    return True


# ==============================================================
# 2. LLMCLIENT SINGLETON & LOCK
# ==============================================================


def test_llmclient_singleton():
    print("\n" + "=" * 60)
    print("TEST: LLMClient singleton and thread-safety lock")
    print("=" * 60)

    from services.llm_service import LLMClient

    LLMClient.reset_instance()

    i1 = LLMClient.get_instance()
    i2 = LLMClient.get_instance()
    check(i1 is i2, "get_instance returns the same object")

    check(hasattr(LLMClient, "_lock"), "_lock class variable exists")
    check(hasattr(LLMClient, "_instance"), "_instance class variable exists")

    LLMClient.reset_instance()
    check(LLMClient._instance is None, "reset_instance clears singleton")

    return True


# ==============================================================
# 3. FALLBACK GENERATION
# ==============================================================


def test_fallback_generation():
    print("\n" + "=" * 60)
    print("TEST: Deterministic fallback generation")
    print("=" * 60)

    from services.llm_service import LLMClient
    from models.schemas import ExtractedSLAData, RiskAnalysisResult

    LLMClient.reset_instance()
    client = LLMClient.get_instance()

    # ExtractedSLAData fallback
    fb_ext = client._generate_fallback(ExtractedSLAData, {})
    check(isinstance(fb_ext, ExtractedSLAData), "ExtractedSLAData fallback type")
    check(fb_ext.supplier_id == "unknown", "ExtractedSLAData fallback supplier_id")
    check(fb_ext.sla_lead_time_hours == 72, "ExtractedSLAData fallback hours")
    check(fb_ext.delay_penalty_rate == 500.0, "ExtractedSLAData fallback delay_penalty")

    # RiskAnalysisResult fallback
    fb_risk = client._generate_fallback(RiskAnalysisResult, {})
    check(isinstance(fb_risk, RiskAnalysisResult), "RiskAnalysisResult fallback type")
    check("DelayEvent" in fb_risk.risks, "RiskAnalysisResult fallback risks")
    check(fb_risk.confidence == 0.5, "RiskAnalysisResult fallback confidence")

    # Fallback text
    fb_text = client._generate_fallback_text({})
    check(fb_text.startswith("[Fallback Response]"), "Fallback text prefix")

    return True


# ==============================================================
# 4. EXTRACTION PIPELINE TOPOLOGY
# ==============================================================


def test_extraction_pipeline_topology():
    print("\n" + "=" * 60)
    print("TEST: Extraction pipeline graph topology")
    print("=" * 60)

    from services.llm_service import build_extraction_graph

    graph = build_extraction_graph()
    check(graph is not None, "build_extraction_graph returns compiled graph")

    # Verify nodes exist by trying to access them
    nodes = list(graph.nodes.keys())
    check("guardrail" in nodes, "Node 'guardrail' registered")
    check("extractor" in nodes, "Node 'extractor' registered")
    check("validator" in nodes, "Node 'validator' registered")

    return True


# ==============================================================
# 5. RISK ENGINE PIPELINE TOPOLOGY
# ==============================================================


def test_risk_engine_topology():
    print("\n" + "=" * 60)
    print("TEST: Risk engine pipeline graph topology")
    print("=" * 60)

    from services.risk_engine_service import build_risk_graph

    graph = build_risk_graph()
    check(graph is not None, "build_risk_graph returns compiled graph")

    nodes = list(graph.nodes.keys())
    check("fetch_sla" in nodes, "Node 'fetch_sla' registered")
    check("analyze_risk" in nodes, "Node 'analyze_risk' registered")
    check("generate_alert" in nodes, "Node 'generate_alert' registered")

    return True


# ==============================================================
# 6. CHAT SERVICE PIPELINE TOPOLOGY
# ==============================================================


def test_chat_pipeline_topology():
    print("\n" + "=" * 60)
    print("TEST: Chat pipeline graph topology")
    print("=" * 60)

    from services.chat_service import build_chat_graph

    graph = build_chat_graph()
    check(graph is not None, "build_chat_graph returns compiled graph")

    nodes = list(graph.nodes.keys())
    check("guardrail" in nodes, "Node 'guardrail' registered")
    check("developer" in nodes, "Node 'developer' registered")
    check("database" in nodes, "Node 'database' registered")
    check("customer_service" in nodes, "Node 'customer_service' registered")

    return True


# ==============================================================
# 7. SEMANTIC LIFTER — NAMESPACE ENFORCEMENT
# ==============================================================


def test_lifter_namespace():
    print("\n" + "=" * 60)
    print("TEST: Semantic lifter namespace enforcement")
    print("=" * 60)

    from services.lifting_service import SemanticLifter
    from models.schemas import ExtractedSLAData

    data = ExtractedSLAData(
        document_id="DOC-001",
        supplier_id="SUP-1",
        supplier_name="Acme Corp",
        material="Titanium",
        sla_lead_time_hours=72,
        delay_penalty_rate=500.0,
        missed_item_penalty_rate=150.0,
        minimum_quality_threshold=0.98,
        quality_penalty_rate=0.15,
    )

    lifter = SemanticLifter()
    sparql = lifter.lift_extracted_data(data)

    check("PREFIX : <http://example.org/ontology#>" in sparql, "SPARQL contains project namespace")
    check("trail1:" not in sparql, "SPARQL does NOT contain banned namespace")
    check(":Supplier" in sparql, "SPARQL creates Supplier individual")
    check(":RawMaterial" in sparql, "SPARQL creates RawMaterial individual")

    return True


# ==============================================================
# 8. HOURS-TO-DAYS CONVERSION
# ==============================================================


def test_hours_to_days():
    print("\n" + "=" * 60)
    print("TEST: Hours-to-days conversion (Integer Day Rule)")
    print("=" * 60)

    from services.lifting_service import SemanticLifter

    check(SemanticLifter._hours_to_days(48) == 2, "48h -> 2 days")
    check(SemanticLifter._hours_to_days(1) == 1, "1h -> 1 day (floor to 1)")
    check(SemanticLifter._hours_to_days(23) == 1, "23h -> 1 day (floor to 1)")
    check(SemanticLifter._hours_to_days(72) == 3, "72h -> 3 days")
    check(SemanticLifter._hours_to_days(0) == 1, "0h -> 1 day (floor to 1)")

    return True


# ==============================================================
# 9. SPARQL ESCAPING
# ==============================================================


def test_sparql_escaping():
    print("\n" + "=" * 60)
    print("TEST: SPARQL literal escaping")
    print("=" * 60)

    from services.lifting_service import _escape_sparql_literal

    check(_escape_sparql_literal("plain") == "plain", "Plain string unchanged")
    check(_escape_sparql_literal('say "hello"') == 'say \\"hello\\"', "Double quotes escaped")
    check(_escape_sparql_literal("line1\nline2") == "line1\\nline2", "Newlines escaped")
    check(_escape_sparql_literal("back\\slash") == "back\\\\slash", "Backslashes escaped")

    return True


# ==============================================================
# 10. BUILD SUPPLIER / MATERIAL URI
# ==============================================================


def test_uri_builders():
    print("\n" + "=" * 60)
    print("TEST: URI helper functions")
    print("=" * 60)

    from services.lifting_service import (
        _build_supplier_uri,
        _build_contract_id,
        _build_material_uri,
    )

    # Supplier URI
    check(
        _build_supplier_uri("SUP_001", "Acme") == "Supplier_SUP_001",
        "Supplier URI with ID",
    )
    check(
        _build_supplier_uri("", "Acme Corp") == "Supplier_Acme_Corp",
        "Supplier URI without ID",
    )
    check(
        _build_supplier_uri("Supplier_XYZ", "Test") == "Supplier_XYZ",
        "Supplier URI with prefix already: Supplier_ prefix check",
    )
    check(
        _build_supplier_uri("BestSupplier", "Best") == "Supplier_BestSupplier",
        "Supplier URI: 'BestSupplier' doesn't start with 'Supplier_' so prefix added",
    )

    # Contract ID
    check(_build_contract_id("SLA-001") == "SLA_001", "Contract ID with dash")
    check(_build_contract_id("EXT_A1B2") == "EXT_A1B2", "Contract ID with underscore")
    check(_build_contract_id("") != "", "Contract ID empty fallback")

    # Material URI
    check(_build_material_uri("Titanium") == "Titanium", "Material URI simple")
    check(_build_material_uri("   ") != "", "Material URI whitespace fallback")

    return True


# ==============================================================
# 11. DASHBOARD ENDPOINT WIRING
# ==============================================================


def test_dashboard_router_wiring():
    print("\n" + "=" * 60)
    print("TEST: Dashboard endpoint wiring")
    print("=" * 60)

    from api.dashboard import router

    routes = [r.path for r in router.routes]
    check("/api/dashboard/risk-scores" in routes, "GET /risk-scores registered")
    check("/api/dashboard/compliance-alerts" in routes, "GET /compliance-alerts registered")
    check("/api/dashboard/fallback-options/{material_id}" in routes, "GET /fallback-options/ registered")
    check("/api/dashboard/chat" in routes, "POST /chat registered")

    return True


# ==============================================================
# 12. SANDBOX ENDPOINT WIRING
# ==============================================================


def test_sandbox_router_wiring():
    print("\n" + "=" * 60)
    print("TEST: Sandbox endpoint wiring")
    print("=" * 60)

    from api.sandbox import router

    routes = [r.path for r in router.routes]
    check("/api/sandbox/upload-sla" in routes, "POST /upload-sla registered")
    check("/api/sandbox/upload-pdf" in routes, "POST /upload-pdf registered")
    check("/api/sandbox/confirm-sla" in routes, "POST /confirm-sla registered")
    check("/api/sandbox/simulate-iot" in routes, "POST /simulate-iot registered")
    check("/api/sandbox/impacted-products" in routes, "GET /impacted-products registered")

    return True


# ==============================================================
# 13. SPARQL INJECTION SAFETY
# ==============================================================


def test_sparql_injection_safety():
    print("\n" + "=" * 60)
    print("TEST: SPARQL injection safety")
    print("=" * 60)

    from services.lifting_service import SemanticLifter
    from models.schemas import ExtractedSLAData

    # Material with characters that could break SPARQL
    data = ExtractedSLAData(
        document_id="DOC-001",
        supplier_id="SUP-1",
        supplier_name='Acme "Corp"',
        material='Titanium "Grade-5"',
        sla_lead_time_hours=72,
        delay_penalty_rate=500.0,
        missed_item_penalty_rate=150.0,
        minimum_quality_threshold=0.98,
        quality_penalty_rate=0.15,
    )

    lifter = SemanticLifter()
    sparql = lifter.lift_extracted_data(data)

    check('"Acme \\"Corp\\""' in sparql, "Supplier name quotes escaped")
    check('"Titanium \\"Grade-5\\""' in sparql, "Material quotes escaped")

    return True


# ==============================================================
# 14. INITIAL STATE CONSTRUCTION
# ==============================================================


def test_initial_state_construction():
    print("\n" + "=" * 60)
    print("TEST: Initial state construction for pipelines")
    print("=" * 60)

    from services.llm_service import _make_initial_state

    state = _make_initial_state("some contract text")
    check(state["raw_document_text"] == "some contract text", "raw_document_text preserved")
    check(state["is_valid_contract"] is False, "is_valid_contract defaults False")
    check(state["extracted_data"] is None, "extracted_data defaults None")
    check(state["iteration_count"] == 0, "iteration_count starts at 0")
    check(state["document_id"].startswith("DOC-"), "document_id auto-generated")

    return True


# ==============================================================
# RUNNER
# ==============================================================

if __name__ == "__main__":
    print("\n  Integration Test Suite — Sprint 3 & 4")
    print("  ====================================")

    test_model_imports()
    test_llmclient_singleton()
    test_fallback_generation()
    test_extraction_pipeline_topology()
    test_risk_engine_topology()
    test_chat_pipeline_topology()
    test_lifter_namespace()
    test_hours_to_days()
    test_sparql_escaping()
    test_uri_builders()
    test_dashboard_router_wiring()
    test_sandbox_router_wiring()
    test_sparql_injection_safety()
    test_initial_state_construction()

    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f"  RESULTS:  {PASS}/{total} passed  |  {FAIL}/{total} failed")
    print("=" * 60)

    sys.exit(0 if FAIL == 0 else 1)
