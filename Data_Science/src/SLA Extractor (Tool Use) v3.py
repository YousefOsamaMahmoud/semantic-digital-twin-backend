# ==========================================
# SEMANTIC DIGITAL TWIN: Autonomous SLA Extractor (LangGraph + Tool Use)
# ==========================================
import os
from pathlib import Path
from dotenv import load_dotenv
import re
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from SPARQLWrapper import SPARQLWrapper, POST

# --- CONFIGURATION ---
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GRAPHDB_UPDATE_ENDPOINT = "http://localhost:7200/repositories/SemanticDigitalTwin/statements"

llm = ChatOpenAI(
    model="deepseek/deepseek-chat", 
    openai_api_key=os.environ["OPENROUTER_API_KEY"],
    openai_api_base=OPENROUTER_BASE_URL,
    temperature=0.0
)

# ==========================================
# 1. TOOL DEFINITION (PYDANTIC SCHEMA)
# ==========================================
# The API guarantees the LLM will return this exact structure and data types.
class ContractData(BaseModel):
    document_id: str = Field(description="The unique Document ID or Reference number.")
    supplier_id: str = Field(description="The name or ID of the supplier/vendor.")
    sla_lead_time_hours: int = Field(description="The delivery lead time converted to hours.")
    delay_penalty_rate: float = Field(description="The financial penalty amount for delayed delivery.")
    missed_item_penalty_rate: float = Field(description="The financial penalty amount for missed/short-shipped items.")
    minimum_quality_threshold: float = Field(description="The minimum quality yield/threshold as a decimal (e.g., 98% = 0.98).")
    quality_penalty_rate: float = Field(description="The penalty rate for poor quality as a decimal (e.g., 15% = 0.15).")

# ==========================================
# 2. STATE DEFINITION
# ==========================================
class ExtractionState(TypedDict):
    raw_document_text: str
    is_valid_contract: bool
    extracted_contract: ContractData  # State now holds the Pydantic object directly!
    error_message: str
    iteration_count: int
    injection_success: bool

# ==========================================
# 3. AGENT NODES
# ==========================================
def document_guardrail_node(state: ExtractionState) -> ExtractionState:
    print("\n[Node 0] Document Security Guardrail")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a document classifier. Read the text and determine if it is a supply chain Service Level Agreement (SLA) or contract. Output ONLY 'VALID' or 'INVALID'."),
        ("human", "{text}")
    ])
    
    response = (prompt | llm).invoke({"text": state["raw_document_text"]}).content.strip().upper()
    
    if "VALID" in response:
        print("    [+] Document Verified: Valid SLA Contract.")
        state["is_valid_contract"] = True
    else:
        print("    [-] Document Rejected: Not an SLA contract.")
        state["is_valid_contract"] = False
        
    return state


def extraction_agent_node(state: ExtractionState) -> ExtractionState:
    print(f"\n[Node 1] Tool-Calling Extractor (Attempt {state.get('iteration_count', 0) + 1})")
    
    # Bind the Pydantic tool to the LLM
    structured_llm = llm.with_structured_output(ContractData)
    
    system_prompt = """You are an expert legal data extraction AI.
Extract the exact financial and logistical parameters from the contract using the provided tool schema.

### PREVIOUS BUSINESS LOGIC ERRORS TO FIX ###
{error_message}"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{text}")
    ])
    
    # The LLM now returns a perfect Python Object, no JSON parsing needed!
    result = (prompt | structured_llm).invoke({
        "text": state["raw_document_text"],
        "error_message": state.get("error_message", "None.")
    })
    
    state["extracted_contract"] = result
    state["iteration_count"] = state.get("iteration_count", 0) + 1
    return state


def business_logic_validator_node(state: ExtractionState) -> ExtractionState:
    print("\n[Node 2] Semantic Business Logic Validator")
    # We no longer check for JSON brackets. We check for real-world logic!
    data = state["extracted_contract"]
    
    try:
        # Business Rule 1: Lead time must be reasonable
        if data.sla_lead_time_hours <= 0:
            raise ValueError("Lead time cannot be 0 or negative. Re-read the contract for the correct hours.")
        
        # Business Rule 2: Decimals should be properly formatted (not > 1 for percentages)
        if data.minimum_quality_threshold > 1.0:
            raise ValueError(f"Quality threshold ({data.minimum_quality_threshold}) is > 1.0. Convert percentages to decimals (e.g., 95% -> 0.95).")
            
        print("    [+] Semantic Data validated: Parameters align with business rules.")
        state["error_message"] = ""
        
    except Exception as e:
        print(f"    [-] Business Logic Error: {e}")
        state["error_message"] = str(e)
        
    return state


def database_injector_node(state: ExtractionState) -> ExtractionState:
    print("\n[Node 3] GraphDB Injection Tool")
    data = state["extracted_contract"]
    
    def clean_uri(text):
        return re.sub(r'[^a-zA-Z0-9_]', '_', str(text))
        
    doc_id = clean_uri(data.document_id)
    sup_id = clean_uri(data.supplier_id)
    
    sparql_update = f"""PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

INSERT DATA {{
    trail1:{doc_id} a trail1:SLA_Agreement ;
        trail1:hasSLALeadTime "{data.sla_lead_time_hours}"^^xsd:integer ;
        trail1:hasDelayPenaltyRate "{data.delay_penalty_rate}"^^xsd:decimal ;
        trail1:hasMissedItemPenaltyRate "{data.missed_item_penalty_rate}"^^xsd:decimal ;
        trail1:hasMinimumQualityThreshold "{data.minimum_quality_threshold}"^^xsd:decimal ;
        trail1:hasQualityPenaltyRate "{data.quality_penalty_rate}"^^xsd:decimal ;
        trail1:governs trail1:{sup_id} .
        
    trail1:{sup_id} trail1:hasSLA trail1:{doc_id} .
}}"""
    
    print(f"    [i] Executing query for Document: {doc_id} | Supplier: {sup_id}")
    
    sparql = SPARQLWrapper(GRAPHDB_UPDATE_ENDPOINT)
    sparql.setQuery(sparql_update)
    sparql.setMethod(POST)
    
    try:
        sparql.query()
        print(f"    [+] SUCCESS! Inserted {doc_id} into GraphDB.")
        state["injection_success"] = True
    except Exception as e:
        print(f"    [-] GraphDB Injection Error: {e}")
        state["injection_success"] = False
        
    return state

# ==========================================
# 4. ROUTING & GRAPH COMPILATION
# ==========================================
def check_validation_success(state: ExtractionState) -> str:
    if state["error_message"] and state["iteration_count"] < 3:
        return "retry_extraction"
    return "inject"

def build_extractor_agent():
    workflow = StateGraph(ExtractionState)
    
    workflow.add_node("guardrail", document_guardrail_node)
    workflow.add_node("extractor", extraction_agent_node)
    workflow.add_node("validator", business_logic_validator_node)
    workflow.add_node("injector", database_injector_node)
    
    workflow.set_entry_point("guardrail")
    workflow.add_conditional_edges("guardrail", lambda state: "extractor" if state["is_valid_contract"] else END)
    workflow.add_edge("extractor", "validator")
    workflow.add_conditional_edges("validator", check_validation_success, {"retry_extraction": "extractor", "inject": "injector"})
    workflow.add_edge("injector", END)
    
    return workflow.compile()

# ==========================================
# MAIN EXECUTION: BATCH INGESTION PIPELINE
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("  SEMANTIC TWIN: BATCH SLA INGESTION PIPELINE (TOOL USE)")
    print("=" * 60)
    
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
    CONTRACTS_DIR = os.path.join(PROJECT_ROOT, "contracts")
    os.makedirs(CONTRACTS_DIR, exist_ok=True)
    
    contract_files = [f for f in os.listdir(CONTRACTS_DIR) if f.endswith(".txt")]
    
    if not contract_files:
        print(f"[-] No .txt files found in {CONTRACTS_DIR}.")
        exit()
        
    print(f"[*] Found {len(contract_files)} contracts to process.\n")
    
    app = build_extractor_agent()
    success_count = 0
    failure_count = 0
    
    for filename in contract_files:
        file_path = os.path.join(CONTRACTS_DIR, filename)
        print(f"\n>> Processing: {filename} {'-'*30}")
        
        with open(file_path, "r", encoding="utf-8") as file:
            contract_text = file.read()
            
        initial_state = {
            "raw_document_text": contract_text,
            "is_valid_contract": False,
            "error_message": "",
            "iteration_count": 0,
            "injection_success": False
        }
        
        final_state = app.invoke(initial_state)
        
        if final_state.get("injection_success"):
            success_count += 1
        else:
            failure_count += 1

    print("\n" + "=" * 60)
    print("  BATCH INGESTION COMPLETE")
    print(f"  Total Processed: {len(contract_files)}")
    print(f"  [+] Successful:  {success_count}")
    print(f"  [-] Failed:      {failure_count}")
    print("=" * 60)