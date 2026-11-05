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
    chat_history: List[Dict[str, str]]  # Active context tracker
    live_schema: str
    generated_sparql: str
    graph_results: List[Dict[str, Any]]
    error_message: str
    iteration_count: int
    final_answer: str
    is_valid_topic: bool 

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
    print(f"\n[Node 0] Security Guardrail")
    
    system_prompt = """You are a strict domain classifier for a Semantic Digital Twin.
If the user's query or the ongoing conversation is related to supply chains, logistics, deliveries, materials, suppliers, penalties, SLAs, or business operations, output exactly 'YES'.
If the query is completely off-topic, output exactly 'NO'."""

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
Translate the user's current question into a valid SPARQL SELECT query. Use the conversation history to resolve pronouns like "them", "their", or "the late ones".

PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

### CONVERSATION HISTORY ###
{chat_history}

### LIVE GRAPHDB SCHEMA ###
{live_schema}

### PREVIOUS ERRORS (If Any) ###
{error_message}

RULES:
1. Return ONLY the raw SPARQL query. NO markdown, NO text formatting.
2. Ensure you use the exact property names from the schema. DO NOT invent properties like `hasName` or `isPerformedBy`.
3. If an error is provided above, FIX the syntax error before returning the new query.
4. CRITICAL ENTITY IDs (NO STRING MATCHING): If the user mentions a specific ID (like "DEL_015", "Delivery_007", "Titanium", or "Supplier_Main"), DO NOT search for it using string filters or invented properties like `hasName` or `hasID`. You MUST format it directly as an instance URI (e.g., trail1:DEL_015 or trail1:Delivery_007) and place it directly into the subject or object position of your triples.
   - Wrong: ?delivery trail1:hasName "DEL_015"
   - Correct: trail1:DEL_015 trail1:transports ?material .5. MULTI-HOP REASONING & MEMORY PERSISTENCE: 
   - To find Suppliers: Deliveries transport Materials, and Materials are supplied by Suppliers.
   - You MUST use this exact structural path to connect deliveries to suppliers: `?delivery trail1:transports ?material . ?material trail1:isSuppliedBy ?supplier .`
   - When answering follow-up questions (e.g., "Are any of them delayed?"), preserve this exact chain from the previous turn.
6. REGEX RESTRICTION: ONLY use regex filters for dynamic delivery statuses (e.g., "delayed", "late", "disrupted"). NEVER use regex filters on supplier URIs, material URIs, or class types.
   - Correct Status Filter: `FILTER(regex(str(?status), "delay", "i"))`
7. USE OPTIONAL: Wrap metadata like dates or statuses in an OPTIONAL {{ }} block so queries do not return 0 rows if a field is missing."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Current Question: {question}")
    ])
    
    # Format running history context for the LLM
    history_str = ""
    for turn in state.get("chat_history", []):
        history_str += f"User: {turn['user']}\nAI: {turn['ai']}\n\n"
    if not history_str:
        history_str = "No prior exchanges in this session."

    chain = prompt | llm 
    response = chain.invoke({
        "question": state["user_question"],
        "chat_history": history_str,
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
        state["error_message"] = "" 
    except Exception as e:
        error_str = str(e)
        print(f"    [!] GraphDB Error Intercepted: {error_str[:100]}...")
        state["error_message"] = error_str
        state["graph_results"] = []
        
    return state


def translate_results_node(state: ChatState) -> ChatState:
    print("\n[Node 3] Customer Service Agent")
    
    if not state.get("is_valid_topic", True):
        state["final_answer"] = "I am a Supply Chain Semantic Assistant. I can only answer questions related to our deliveries, suppliers, materials, and SLA agreements. How can I help you with our logistics today?"
        return state
    
    if state["error_message"] and state["iteration_count"] >= 3:
        state["final_answer"] = "I apologize, but I encountered a complex database error while trying to retrieve that information and couldn't resolve it."
        return state

    system_prompt = """You are a professional supply chain assistant.
Answer the user's current question using the provided database results and conversation history to maintain context.
If the results are empty, clearly state that no matching data was found.
CRITICAL RULE: List every single entity returned. Keep descriptions brief, natural, and complete. Do not mention technical terms like SPARQL or JSON."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Conversation History:\n{history}\n\nCurrent Question: {question}\n\nDatabase Results:\n{data}")
    ])
    
    history_str = ""
    for turn in state.get("chat_history", []):
        history_str += f"User: {turn['user']}\nAI: {turn['ai']}\n\n"

    chain = prompt | llm
    response = chain.invoke({
        "question": state["user_question"],
        "history": history_str if history_str else "Beginning of chat.",
        "data": json.dumps(state["graph_results"], indent=2) if state["graph_results"] else "EMPTY RESULTS."
    })
    
    state["final_answer"] = response.content.strip()
    return state


# ==========================================
# 4. GRAPH ROUTING LOGIC
# ==========================================
def should_retry(state: ChatState) -> str:
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
    
    # --- FIXED: Persistent history allocated OUTSIDE loop ---
    session_history = []
    
    print("\n[ Ready. Type your questions below. Type 'exit' to quit. ]")
    
    while True:
        user_input = input("\n👤 You: ")
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Shutting down Semantic Chat...")
            break
            
        if not user_input.strip():
            continue
            
        # --- FIXED: Injected the live session tracking array ---
        initial_state = {
            "user_question": user_input,
            "chat_history": session_history, 
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
        
        # --- FIXED: Save the exchange so the NEXT turn remembers it ---
        session_history.append({
            "user": user_input,
            "ai": final_state["final_answer"]
        })