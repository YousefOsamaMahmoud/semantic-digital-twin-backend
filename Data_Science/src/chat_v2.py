# ==========================================
# SEMANTIC DIGITAL TWIN: LangGraph Self-Correcting SPARQL Agent
# ==========================================
import os
from pathlib import Path
from dotenv import load_dotenv
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from SPARQLWrapper import SPARQLWrapper, JSON

# --- CONFIGURATION ---
# Using OpenRouter and DeepSeek V3
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/SemanticDigitalTwin"
ONTOLOGY_PREFIX = "http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#"

llm = ChatOpenAI(
    model="deepseek/deepseek-chat", 
    openai_api_key=os.environ["OPENROUTER_API_KEY"],
    openai_api_base=OPENROUTER_BASE_URL,
    temperature=0.0,
    max_tokens=800
)

# ==========================================
# 1. STATE DEFINITION
# ==========================================
class ChatState(TypedDict):
    user_question: str
    live_schema: str
    generated_sparql: str
    graph_results: List[Dict[str, Any]]
    error_message: str
    iteration_count: int
    final_answer: str
    is_valid_topic: bool  # NEW: Tracks if the question is supply chain related

# ==========================================
# 2. SCHEMA EXTRACTION (Runs once at boot)
# ==========================================
def fetch_live_schema() -> str:
    print("\n[*] Booting up... Extracting Schema from GraphDB...")
    schema_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?type ?entity WHERE {
      { ?entity a owl:Class . BIND("Class" AS ?type) }
      UNION { ?entity a owl:ObjectProperty . BIND("ObjectProperty" AS ?type) }
      UNION { ?entity a owl:DatatypeProperty . BIND("DataProperty" AS ?type) }
      FILTER(STRSTARTS(STR(?entity), "http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#"))
    }
    """
    sparql = SPARQLWrapper(GRAPHDB_ENDPOINT)
    sparql.setQuery(schema_query)
    sparql.setReturnFormat(JSON)
    sparql.setMethod('POST')
    
    try:
        results = sparql.query().convert()["results"]["bindings"]
        classes, obj_props, data_props = [], [], []
        for b in results:
            entity_type = b["type"]["value"]
            entity_name = b["entity"]["value"].replace(ONTOLOGY_PREFIX, "trail1:")
            if entity_type == "Class": classes.append(entity_name)
            elif entity_type == "ObjectProperty": obj_props.append(entity_name)
            elif entity_type == "DataProperty": data_props.append(entity_name)
                
        schema_string = f"CLASSES:\n{', '.join(classes)}\n\nOBJECT PROPERTIES:\n{', '.join(obj_props)}\n\nDATA PROPERTIES:\n{', '.join(data_props)}"
        return schema_string
    except Exception as e:
        print("[-] Schema extraction failed:", e)
        return "ERROR EXTRACTING SCHEMA"

# ==========================================
# 3. GRAPH NODES (The Agents)
# ==========================================

def guardrail_node(state: ChatState) -> ChatState:
    """NEW NODE: Checks if the question is actually related to the supply chain."""
    print(f"\n[Node 0] Security Guardrail")
    
    system_prompt = """You are a strict domain classifier for a Semantic Digital Twin.
If the user's query is related to supply chains, logistics, deliveries, materials, suppliers, penalties, SLAs, or business operations, output exactly 'YES'.
If the query is off-topic (e.g., cooking, politics, casual chat, general knowledge), output exactly 'NO'."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"question": state["user_question"]}).content.strip().upper()
    
    if "YES" in response:
        print("    [+] Topic Approved: Proceeding to database translation.")
        state["is_valid_topic"] = True
    else:
        print("    [-] Topic Rejected: Out of domain.")
        state["is_valid_topic"] = False
        
    return state


def generate_sparql_node(state: ChatState) -> ChatState:
    print(f"\n[Node 1] SPARQL Developer Agent (Attempt {state['iteration_count'] + 1})")
    
    system_prompt = """You are an expert Semantic Web Developer.
Translate the user's natural language question into a valid SPARQL SELECT query.

PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

### LIVE GRAPHDB SCHEMA ###
{live_schema}

### PREVIOUS ERRORS (If Any) ###
{error_message}

RULES:
1. Return ONLY the raw SPARQL query. NO markdown, NO text formatting.
2. Ensure you use the exact property names from the schema.
3. If an error is provided above, FIX the syntax error before returning the new query.
4. CRITICAL IDs: If the user asks about a specific entity ID (like "Delivery_007", "Titanium", or "Supplier_Main"), you MUST treat it as a URI instance (e.g., trail1:Delivery_007) in your WHERE clause. Do NOT treat it as a string.
5. MULTI-HOP REASONING: 
   - To find Suppliers: Deliveries transport Materials, and Materials are supplied by Suppliers. 
   - To find Affected Assembly Lines / Processes: Deliveries transport Materials, and Materials affect Processes (trail1:affectsProcess ?process). 
   - CRITICAL: The `?process` variable ITSELF represents the assembly line! Do NOT add extra hops like `isPerformedBy` or `FinalAssembly`.
6. STRING COMPARISONS: When filtering by string values, always wrap the variable in STR(). Example: FILTER(STR(?status) = "Delayed").
7. USE OPTIONAL: If fetching extra context (dates, reason codes), wrap those triples in an OPTIONAL {{ }} block.
8. KEEP QUERIES MINIMAL: Do NOT add hypothetical filters. If a user asks "If Delivery 007 is delayed, what is affected?", just map the physical connection (Delivery -> Material -> Process). Do NOT add a filter checking if the status is actually "Delayed". Do NOT add extra class filters. Stop overcomplicating it!"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}")
    ])
    
    chain = prompt | llm 
    response = chain.invoke({
        "question": state["user_question"],
        "live_schema": state["live_schema"],
        "error_message": f"Previous Error to fix:\n{state['error_message']}" if state.get("error_message") else "None. First attempt."
    })
    
    raw_query = response.content.replace("```sparql", "").replace("```", "").strip()
    if "PREFIX trail1:" not in raw_query:
        raw_query = "PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n" + raw_query
        
    print("    [+] Generated Query:\n", raw_query)
    
    state["generated_sparql"] = raw_query
    state["iteration_count"] += 1
    return state


def execute_sparql_node(state: ChatState) -> ChatState:
    print("\n[Node 2] Database Execution Tool")
    sparql = SPARQLWrapper(GRAPHDB_ENDPOINT)
    sparql.setQuery(state["generated_sparql"])
    sparql.setReturnFormat(JSON)
    sparql.setMethod('POST')
    
    try:
        results = sparql.query().convert()["results"]["bindings"]
        print(f"    [+] Query successful. Found {len(results)} rows.")
        state["graph_results"] = results
        state["error_message"] = "" # Clear any previous errors
    except Exception as e:
        error_str = str(e)
        print(f"    [!] GraphDB Error Intercepted: {error_str[:100]}...")
        state["error_message"] = error_str
        state["graph_results"] = []
        
    return state


def translate_results_node(state: ChatState) -> ChatState:
    print("\n[Node 3] Customer Service Agent")
    
    # 1. Handle Out of Domain gracefully
    if not state.get("is_valid_topic", True):
        state["final_answer"] = "I am a Supply Chain Semantic Assistant. I can only answer questions related to our deliveries, suppliers, materials, and SLA agreements. How can I help you with our logistics today?"
        return state
    
    # 2. Handle persistent errors
    if state["error_message"] and state["iteration_count"] >= 3:
        state["final_answer"] = "I apologize, but I encountered a complex database error while trying to retrieve that information and couldn't resolve it."
        return state

    # 3. Standard translation
    system_prompt = """You are a professional supply chain assistant.
Answer the user's question using ONLY the provided database JSON results. 
If the results are empty, clearly state that no data matching their request was found in the system.
CRITICAL RULE: If the database returns multiple rows/entities, you MUST list every single one of them. Do not summarize or leave any entities out.
Do not mention SPARQL, JSON, or GraphDB. Keep the descriptions brief but complete."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "User Question: {question}\n\nDatabase Results:\n{data}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({
        "question": state["user_question"],
        "data": json.dumps(state["graph_results"], indent=2) if state["graph_results"] else "EMPTY RESULTS. No data found."
    })
    
    state["final_answer"] = response.content.strip()
    return state


# ==========================================
# 4. GRAPH ROUTING LOGIC
# ==========================================
def should_retry(state: ChatState) -> str:
    """Decides whether to loop back and fix code or proceed."""
    if state.get("error_message") != "" and state["iteration_count"] < 3:
        print("\n    [Router] SYNTAX ERROR DETECTED -> Routing back to Developer Agent for self-correction.")
        return "retry"
    print("\n    [Router] QUERY SUCCESS (Or max retries reached) -> Routing to Customer Service.")
    return "translate"

def build_chat_agent():
    workflow = StateGraph(ChatState)
    
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("developer", generate_sparql_node)
    workflow.add_node("database", execute_sparql_node)
    workflow.add_node("customer_service", translate_results_node)
    
    workflow.set_entry_point("guardrail")
    
    # NEW ROUTING: If valid topic, go to developer. If not, go straight to Customer Service.
    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "developer" if state["is_valid_topic"] else "customer_service",
        {
            "developer": "developer",
            "customer_service": "customer_service"
        }
    )
    
    workflow.add_edge("developer", "database")
    
    workflow.add_conditional_edges(
        "database",
        should_retry,
        {
            "retry": "developer",
            "translate": "customer_service"
        }
    )
    workflow.add_edge("customer_service", END)
    
    return workflow.compile()

# ==========================================
# MAIN EXECUTION: INTERACTIVE TERMINAL
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("  SEMANTIC TWIN: INTERACTIVE AI CHAT AGENT")
    print("=" * 60)
    
    schema = fetch_live_schema()
    agent_app = build_chat_agent()
    
    print("\n[ Ready. Type your questions below. Type 'exit' to quit. ]")
    
    while True:
        user_input = input("\n👤 You: ")
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Shutting down Semantic Chat...")
            break
            
        if not user_input.strip():
            continue
            
        initial_state = {
            "user_question": user_input,
            "live_schema": schema,
            "generated_sparql": "",
            "graph_results": [],
            "error_message": "",
            "iteration_count": 0,
            "final_answer": "",
            "is_valid_topic": True
        }
        
        final_state = agent_app.invoke(initial_state)
        
        print(f"\n🤖 AI: {final_state['final_answer']}")
        print("-" * 60)