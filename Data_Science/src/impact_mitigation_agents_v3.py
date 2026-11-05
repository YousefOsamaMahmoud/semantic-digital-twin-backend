# ==========================================
# SEMANTIC DIGITAL TWIN: Multi-Agent Risk Router (LangGraph + Tool Use)
# ==========================================
import os
from pathlib import Path
from dotenv import load_dotenv
import json
import time
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from SPARQLWrapper import SPARQLWrapper, JSON

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GRAPHDB_QUERY_ENDPOINT = "http://localhost:7200/repositories/SemanticDigitalTwin"
GRAPHDB_UPDATE_ENDPOINT = f"{GRAPHDB_QUERY_ENDPOINT}/statements"

# Use OpenRouter with DeepSeek
llm = ChatOpenAI(
    model="deepseek/deepseek-chat",
    openai_api_key=os.environ["OPENROUTER_API_KEY"],
    openai_api_base=OPENROUTER_BASE_URL,
    temperature=0.0,
    max_tokens=800
)

# ------------------------------------------
# 1. TOOL DEFINITION (PYDANTIC SCHEMA)
# ------------------------------------------
class RiskDetails(BaseModel):
    SLAViolation: bool = Field(default=False)
    ProductionDisruption: bool = Field(default=False)
    DelayEvent: bool = Field(default=False)

class RiskAnalysis(BaseModel):
    risks: List[str] = Field(description="List of active risk types, e.g., ['DelayEvent', 'SLAViolation', 'ProductionDisruption']")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    risk_details: RiskDetails = Field(description="Boolean flags for specific risk types")
    severity: str = Field(description="Severity level: 'Low', 'Medium', 'High', or 'Critical'")
    financial_penalty_estimate: float = Field(description="Estimated financial penalty amount")
    reasoning: str = Field(description="Brief explanation of the risk analysis and mitigation reasoning")


# ------------------------------------------
# 2. STATE DEFINITION
# ------------------------------------------
class RiskPipelineState(TypedDict):
    delivery_id: str
    delay_hours: int
    reason_code: str
    injection_success: bool
    ontology_risks: List[str]
    context_data: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    target_managers: List[str]
    alerts: Dict[str, str]
    alerts_validated: bool

# ------------------------------------------
# NODE 1: ML PREDICTION SIMULATOR
# ------------------------------------------
def read_iot_telemetry(state: RiskPipelineState) -> RiskPipelineState:
    print("\n" + "=" * 50)
    print("[1/7] IoT SIMULATOR: Checking for predicted delays...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    iot_file = os.path.join(script_dir, "..", "data_Lake", "iot_streams", "telemetry_stream_001.json")
    
    try:
        with open(iot_file, "r") as f:
            telemetry = json.load(f)
        latest = telemetry[-1]
        delivery_id = latest.get("delivery_id", "DEL_005")
        delay_hours = latest.get("estimated_delay_hours", 0)
        reason = latest.get("reason_code", "Unknown")
    except Exception:
        print("    (File not found, using fallback DEL_005)")
        delivery_id = "DEL_005"
        delay_hours = 36
        reason = "Transport/Weather"
        
    state["delivery_id"] = delivery_id
    state["delay_hours"] = delay_hours
    state["reason_code"] = reason
    print(f"    Detected: {delivery_id}, {delay_hours}h delay, reason: {reason}")
    return state

# ------------------------------------------
# NODE 2: GRAPHDB INJECTION + REASONER TRIGGER
# ------------------------------------------
def inject_and_reason_in_graphdb(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[2/7] GRAPHDB: Injecting DelayEvent...")
    delivery_id = state["delivery_id"]
    delay_hours = state["delay_hours"]
    reason = state["reason_code"]
    
    risk_id = f"Risk_ML_{int(time.time())}"
    
    insert_query = f"""
    PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    INSERT DATA {{
        trail1:{risk_id} a trail1:DelayEvent ;
            trail1:affectsDelivery trail1:{delivery_id} ;
            trail1:hasDelayDuration "{delay_hours}"^^xsd:integer ;
            trail1:hasReasonCode "{reason}"^^xsd:string ;
            trail1:hasRiskStatus "Predicted"^^xsd:string .
        trail1:{delivery_id} trail1:hasDeliveryStatus "Delayed"^^xsd:string .
    }}
    """
    sparql = SPARQLWrapper(GRAPHDB_UPDATE_ENDPOINT)
    sparql.setQuery(insert_query)
    sparql.setMethod("POST")
    
    success = True
    try:
        sparql.query()
        print(f"    Inserted {risk_id} successfully.")
    except Exception as e:
        print(f"    WARNING: Could not insert into GraphDB: {e}")
        success = False
        
    state["injection_success"] = success
    time.sleep(0.5)
    return state

# ------------------------------------------
# NODE 3: CONTEXT GATHERING (SPARQL + ONTOLOGY)
# ------------------------------------------
def query_ontology_context(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[3/7] KNOWLEDGE GRAPH: Querying inferred risks & context...")
    delivery_id = state["delivery_id"]
    
    sparql = SPARQLWrapper(GRAPHDB_QUERY_ENDPOINT)
    sparql.setReturnFormat(JSON)
    
    query_risks = f"""
    PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
    SELECT DISTINCT ?riskType WHERE {{
        ?riskEvent trail1:affectsDelivery trail1:{delivery_id} ;
                   a ?riskType .
        FILTER(?riskType IN (
            trail1:DelayEvent,
            trail1:SLAViolation,
            trail1:ProductionDisruption
        ))
    }}
    """
    sparql.setQuery(query_risks)
    ontology_risks = []
    try:
        results = sparql.query().convert()["results"]["bindings"]
        for res in results:
            ontology_risks.append(res["riskType"]["value"].split("#")[-1])
        print(f"    Ontology inferred: {ontology_risks if ontology_risks else 'none'}")
    except Exception as e:
        print(f"    WARNING: SPARQL query failed: {e}")
        
    context_data = {}
    query_context = f"""
    PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
    SELECT DISTINCT ?penaltyAmount ?slaLeadTime ?stock ?safe ?disruptionLevel
    WHERE {{
        trail1:{delivery_id} trail1:transports ?material .
        ?material trail1:isSuppliedBy ?supplier .
        ?supplier trail1:hasSLA ?sla .
        ?sla trail1:hasSLALeadTime ?slaLeadTime .
        
        OPTIONAL {{ trail1:{delivery_id} trail1:hasPenaltyAmount ?penaltyAmount . }}
        
        OPTIONAL {{ 
            ?material trail1:affectsProcess ?process .
            ?process a trail1:ProductionDisruption ;
                     trail1:hasCriticalityLevel ?disruptionLevel .
        }}
        
        OPTIONAL {{ ?material trail1:hasInventoryStock ?stock ;
                             trail1:hasSafetyStockLevel ?safe . }}
    }}
    LIMIT 1
    """
    sparql.setQuery(query_context)
    try:
        results = sparql.query().convert()["results"]["bindings"]
        if results:
            row = results[0]
            context_data["sla_lead_time"] = int(row.get("slaLeadTime", {}).get("value", 10))
            context_data["inventory_stock"] = int(row.get("inventoryStock", {}).get("value", 50))
            context_data["safety_stock"] = int(row.get("safetyStock", {}).get("value", 100))
            context_data["penalty_rate"] = float(row.get("penaltyRate", {}).get("value", 500))
            print(f"    Context: SLA lead={context_data['sla_lead_time']} days, stock={context_data['inventory_stock']}, penalty=${context_data['penalty_rate']}/day")
    except Exception as e:
        print(f"    WARNING: Could not fetch context: {e}")
        context_data = {"sla_lead_time": 7, "inventory_stock": 80, "safety_stock": 100, "penalty_rate": 500}
        
    state["ontology_risks"] = ontology_risks
    state["context_data"] = context_data
    return state

# ------------------------------------------
# NODE 4: RISK ANALYST AGENT (TOOL USE UPGRADED)
# ------------------------------------------
RISK_ANALYST_PROMPT = """
You are a Supply Chain Risk Analyst. Your job is to determine which business risks actually exist for a delivery based on the Context Data.

<Ontology Inferred Risks>
{ontology_risks}
</Ontology Inferred Risks>

<Delivery Context>
Delivery: {delivery_id}
Delay: {delay_hours} hours ({delay_days:.1f} days)
Reason: {reason_code}
SLA Lead Time: {sla_lead_time} days
Current Inventory Stock: {inventory_stock} units
Safety Stock Level: {safety_stock} units
Daily Penalty Rate: ${penalty_rate}
</Delivery Context>
"""

def risk_analyst_agent(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[4/7] RISK ANALYST AGENT: Reasoning about actual risks (Using Structured Output Tool)...")
    ontology_risks = state.get("ontology_risks", [])
    ctx = state["context_data"]
    delay_hours = state["delay_hours"]
    delay_days = delay_hours / 24.0
    
    # Bind the Pydantic schema Tool to the LLM
    structured_llm = llm.with_structured_output(RiskAnalysis)
    
    prompt = ChatPromptTemplate.from_messages([("system", RISK_ANALYST_PROMPT)])
    chain = prompt | structured_llm
    
    try:
        response = chain.invoke({
            "ontology_risks": json.dumps(ontology_risks) if ontology_risks else "None",
            "delivery_id": state["delivery_id"],
            "delay_hours": delay_hours,
            "delay_days": delay_days,
            "reason_code": state["reason_code"],
            "sla_lead_time": ctx["sla_lead_time"],
            "inventory_stock": ctx["inventory_stock"],
            "safety_stock": ctx["safety_stock"],
            "penalty_rate": ctx["penalty_rate"]
        })
        
        # Convert the Pydantic Object to a dictionary so the rest of the nodes function exactly as before
        analysis = response.model_dump()
        print(f"    Analysis Generated Successfully: {analysis['risks']} | Severity: {analysis['severity']}")
        
    except Exception as e:
        print(f"    WARNING: LLM risk analysis failed ({e}). Using fallback.")
        analysis = {"risks": ["DelayEvent"], "severity": "Low", "reasoning": "Fallback used.", "financial_penalty_estimate": 0}
        
    state["risk_analysis"] = analysis
    return state

# ------------------------------------------
# NODE 5: ROUTER
# ------------------------------------------
def router(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[5/7] ROUTER: Deciding which managers to alert...")
    analysis = state["risk_analysis"]
    active_risks = analysis.get("risks", [])
    
    targets = set()
    if "DelayEvent" in active_risks or "ProductionDisruption" in active_risks:
        targets.add("Production Manager")
    if "SLAViolation" in active_risks:
        targets.add("Procurement Manager")
    if "ProductionDisruption" in active_risks:
        targets.add("Logistics Manager")
        
    state["target_managers"] = list(targets)
    print(f"    Alerted managers: {state['target_managers']}")
    return state

# ------------------------------------------
# NODE 6: MANAGER ALERT AGENTS
# ------------------------------------------
ALERT_PROMPTS = {
    "Production Manager": """You are an urgent alert writer for a PRODUCTION MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Reasoning: {reasoning}. \
Write a 2 sentence alert focusing on potential assembly line stoppages and inventory impact.""",

    "Procurement Manager": """You are an urgent alert writer for a PROCUREMENT MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Financial penalty estimate: ${penalty}. \
Write a 2 sentence alert focusing on SLA breach and financial consequences.""",

    "Logistics Manager": """You are an urgent alert writer for a LOGISTICS MANAGER. \
Context: Delivery {delivery_id} has triggered risks: {risks}. \
Severity: {severity}. Reason: {reason_code}. \
Write a 2 sentence alert focusing on transport issues and rerouting possibilities."""
}

def generate_manager_alerts(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[6/7] ALERT GENERATION: Writing manager-specific alerts...")
    alerts = {}
    analysis = state["risk_analysis"]
    delivery_id = state["delivery_id"]
    
    for manager in state["target_managers"]:
        prompt_template = ALERT_PROMPTS[manager]
        prompt = ChatPromptTemplate.from_messages([("system", prompt_template)])
        chain = prompt | llm
        
        try:
            response = chain.invoke({
                "delivery_id": delivery_id,
                "risks": ", ".join(analysis.get("risks", [])),
                "severity": analysis.get("severity", "Unknown"),
                "reasoning": analysis.get("reasoning", ""),
                "penalty": analysis.get("financial_penalty_estimate", 0),
                "reason_code": state.get("reason_code", "")
            })
            alert_text = response.content.strip()
            print(f"    Generated alert for {manager}: \n      {alert_text}")
        except Exception as e:
            print(f"    WARNING: Failed to generate alert for {manager}: {e}")
            alert_text = f"ALERT: {manager} - delivery {delivery_id} at risk. Check dashboard."
            
        alerts[manager] = alert_text
        
    state["alerts"] = alerts
    return state

# ------------------------------------------
# NODE 7: VALIDATOR AGENT
# ------------------------------------------
VALIDATOR_PROMPT = """You are an alert quality inspector. \
Check the following alert message for a {manager_title}. \
Is it specific, urgent, and factually consistent with the risk reasoning? \
If it is acceptable, reply with "VALID". \
If it is too vague, contains made-up information, or is not urgent enough, reply with "INVALID: <reason>".
Alert: {alert_text}
Original risk context: {risks}, severity {severity}, reasoning: {reasoning}"""

def validate_alerts(state: RiskPipelineState) -> RiskPipelineState:
    print("\n[7/7] VALIDATOR AGENT: Checking alert quality...")
    analysis = state["risk_analysis"]
    
    for manager, alert_text in state["alerts"].items():
        prompt = ChatPromptTemplate.from_messages([("system", VALIDATOR_PROMPT)])
        chain = prompt | llm
        try:
            response = chain.invoke({
                "manager_title": manager,
                "alert_text": alert_text,
                "risks": ", ".join(analysis.get("risks", [])),
                "severity": analysis.get("severity", ""),
                "reasoning": analysis.get("reasoning", "")
            })
            verdict = response.content.strip()
            print(f"    {manager}: {verdict}")
        except Exception as e:
            print(f"    WARNING: Validation failed for {manager}: {e}")
            
    state["alerts_validated"] = True
    return state

# ------------------------------------------
# BUILD THE GRAPH
# ------------------------------------------
def build_pipeline():
    workflow = StateGraph(RiskPipelineState)
    workflow.add_node("iot_simulator", read_iot_telemetry)
    workflow.add_node("graphdb_injector", inject_and_reason_in_graphdb)
    workflow.add_node("context_query", query_ontology_context)
    workflow.add_node("risk_analyst", risk_analyst_agent)
    workflow.add_node("router", router)
    workflow.add_node("alert_generator", generate_manager_alerts)
    workflow.add_node("validator", validate_alerts)
    
    workflow.set_entry_point("iot_simulator")
    workflow.add_edge("iot_simulator", "graphdb_injector")
    workflow.add_edge("graphdb_injector", "context_query")
    workflow.add_edge("context_query", "risk_analyst")
    workflow.add_edge("risk_analyst", "router")
    
    workflow.add_conditional_edges(
        "router",
        lambda state: "generate" if state["target_managers"] else "end",
        {
            "generate": "alert_generator",
            "end": END
        }
    )
    workflow.add_edge("alert_generator", "validator")
    workflow.add_edge("validator", END)
    
    return workflow.compile()

# ------------------------------------------
# MAIN EXECUTION (System Timer + Notifications)
# ------------------------------------------
if __name__ == "__main__":
    
    print("=" * 60)
    print("  SEMANTIC TWIN: AUTOMATED SYSTEM TIMER STARTED")
    print("=" * 60)
    
    app = build_pipeline()
    
    while True:
        print("\n⏳ [SYSTEM TIMER] Initiating scheduled risk analysis job...")
        
        final_state = app.invoke({})
        
        print("\n" + "=" * 60)
        print("  PIPELINE COMPLETE - Waiting for next cycle...")
        print("=" * 60)
        print(f"Delivery ID: {final_state.get('delivery_id', 'Unknown')}")
        print(f"Alerts sent to: {final_state.get('target_managers', [])}")
        
        time.sleep(60)