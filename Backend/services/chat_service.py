# ============================================================
# services/chat_service.py — Layer 2: NL-to-SPARQL Chat Agent
#
# Multi-agent LangGraph pipeline that translates natural-language
# supply-chain questions into SPARQL, executes them against
# GraphDB, and returns a human-readable answer.
#
# Graph topology (mirrors Data_Science_Team chat_v2.py)
# -------------------------------------------------------
#     ENTRY -> [guardrail] --(off-topic)--> [customer_service]
#                |
#                +--(valid)--> [developer] -> [database]
#                                              |
#                                     +-------+--------+
#                                     | (error & < 3) | (success)
#                                     v                v
#                                 [developer]    [customer_service] -> END
# ============================================================

import json
import logging
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES
from services.llm_service import LLMClient

logger = logging.getLogger(__name__)


# ==============================================================
# 1. STATE DEFINITION
# ==============================================================


class ChatState(TypedDict):
    user_question: str
    live_schema: str
    generated_sparql: str
    graph_results: list[dict[str, Any]]
    error_message: str
    iteration_count: int
    final_answer: str
    is_valid_topic: bool


# ==============================================================
# 2. SCHEMA EXTRACTION
# ==============================================================


def fetch_live_schema() -> str:
    """Query GraphDB for the ontology schema (classes + properties)."""
    schema_query = f"""
    {PREFIXES}
    SELECT ?type ?entity WHERE {{
      {{ ?entity a owl:Class . BIND("Class" AS ?type) }}
      UNION {{ ?entity a owl:ObjectProperty . BIND("ObjectProperty" AS ?type) }}
      UNION {{ ?entity a owl:DatatypeProperty . BIND("DataProperty" AS ?type) }}
      FILTER(STRSTARTS(STR(?entity), "http://example.org/ontology#"))
    }}
    """
    try:
        results = graphdb.execute_sparql_select(schema_query)
        classes, obj_props, data_props = [], [], []
        for row in results:
            entity_type = row["type"]
            entity_name = row["entity"].replace(
                "http://example.org/ontology#", ":"
            )
            if entity_type == "Class":
                classes.append(entity_name)
            elif entity_type == "ObjectProperty":
                obj_props.append(entity_name)
            elif entity_type == "DataProperty":
                data_props.append(entity_name)

        schema_string = (
            f"CLASSES:\n{', '.join(classes)}\n\n"
            f"OBJECT PROPERTIES:\n{', '.join(obj_props)}\n\n"
            f"DATA PROPERTIES:\n{', '.join(data_props)}"
        )
        return schema_string
    except Exception as exc:
        logger.warning(
            "Schema extraction failed (%s). Using fallback schema.", exc
        )
        return "SCHEMA UNAVAILABLE -- fallback mode."


# ==============================================================
# 3. LANGGRAPH NODES
# ==============================================================


def guardrail_node(state: ChatState) -> ChatState:
    """Node 0 -- Domain guardrail: is the question supply-chain related?"""
    logger.info("[Chat Node 0] Domain Guardrail")

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a strict domain classifier for a Semantic Digital Twin. "
            "If the user's query is related to supply chains, logistics, deliveries, "
            "materials, suppliers, penalties, SLAs, or business operations, output "
            "exactly 'YES'. If the query is off-topic (e.g., cooking, politics, "
            "casual chat, general knowledge), output exactly 'NO'.",
        ),
        ("human", "{question}"),
    ])

    response = (
        LLMClient.get_instance()
        .invoke_text(prompt, {"question": state["user_question"]})
        .strip()
        .upper()
    )

    FALLBACK_MARKER = "[FALLBACK RESPONSE]"
    if response.startswith(FALLBACK_MARKER):
        logger.info("    LLM unreachable (fallback) -- accepting topic.")
        state["is_valid_topic"] = True
    elif "YES" in response:
        logger.info("    [+] Topic approved.")
        state["is_valid_topic"] = True
    else:
        logger.info("    [-] Topic rejected (out of domain).")
        state["is_valid_topic"] = False

    return state


def generate_sparql_node(state: ChatState) -> ChatState:
    """Node 1 -- SPARQL developer agent: NL -> SPARQL translation."""
    attempt = state["iteration_count"] + 1
    logger.info("[Chat Node 1] SPARQL Developer (Attempt %d)", attempt)

    system_prompt = """You are an expert Semantic Web Developer.
Translate the user's natural language question into a valid SPARQL SELECT query.

PREFIX : <http://example.org/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

### LIVE GRAPHDB SCHEMA ###
{live_schema}

### PREVIOUS ERRORS (If Any) ###
{error_message}

RULES:
1. Return ONLY the raw SPARQL query. NO markdown, NO text formatting.
2. Ensure you use the exact property names from the schema.
3. If an error is provided above, FIX the syntax error before returning the new query.
4. CRITICAL IDs: If the user asks about a specific entity ID (like "Delivery_007" or "Supplier_Main"), you MUST treat it as a URI instance (e.g., :Delivery_007) in your WHERE clause. Do NOT treat it as a string.
5. MULTI-HOP REASONING: To find Suppliers: Deliveries transport Materials, and Materials are supplied by Suppliers. To find Affected Assembly Lines / Processes: Deliveries transport Materials, and Materials affect Processes (:affectsProcess ?process).
6. STRING COMPARISONS: When filtering by string values, always wrap the variable in STR(). Example: FILTER(STR(?status) = "Delayed").
7. USE OPTIONAL: If fetching extra context (dates, reason codes), wrap those triples in an OPTIONAL {{ }} block.
8. KEEP QUERIES MINIMAL: Do NOT add hypothetical filters. If a user asks 'If Delivery 007 is delayed, what is affected?', just map the physical connection (Delivery -> Material -> Process). Do NOT add a filter checking if the status is actually 'Delayed'. Do NOT add extra class filters."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}"),
    ])

    response = LLMClient.get_instance().invoke_text(
        prompt,
        {
            "question": state["user_question"],
            "live_schema": state.get("live_schema", "SCHEMA UNAVAILABLE"),
            "error_message": (
                f"Previous Error to fix:\n{state['error_message']}"
                if state.get("error_message")
                else "None. First attempt."
            ),
        },
    )

    raw_query = (
        response.replace("```sparql", "").replace("```", "").strip()
    )
    if "PREFIX :" not in raw_query:
        raw_query = (
            "PREFIX : <http://example.org/ontology#>\n"
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
            + raw_query
        )

    logger.info("    Generated query:\n%s", raw_query)

    state["generated_sparql"] = raw_query
    state["iteration_count"] = attempt
    return state


def execute_sparql_node(state: ChatState) -> ChatState:
    """Node 2 -- Database execution: run the SPARQL against GraphDB."""
    logger.info("[Chat Node 2] Database Execution")

    try:
        results = graphdb.execute_sparql_select(state["generated_sparql"])
        logger.info("    Query successful. Found %d rows.", len(results))
        state["graph_results"] = results
        state["error_message"] = ""
    except Exception as exc:
        error_str = str(exc)
        logger.warning("    GraphDB error: %.120s", error_str)
        state["error_message"] = error_str
        state["graph_results"] = []

    return state


def translate_results_node(state: ChatState) -> ChatState:
    """Node 3 -- Customer service agent: SPARQL results -> NL."""
    logger.info("[Chat Node 3] Customer Service")

    if not state.get("is_valid_topic", True):
        state["final_answer"] = (
            "I am a Supply Chain Semantic Assistant. I can only answer questions "
            "related to our deliveries, suppliers, materials, and SLA agreements. "
            "How can I help you with our logistics today?"
        )
        return state

    if state["error_message"] and state["iteration_count"] >= 3:
        state["final_answer"] = (
            "I apologize, but I encountered a complex database error while trying "
            "to retrieve that information and couldn't resolve it."
        )
        return state

    system_prompt = """You are a professional supply chain assistant.
Answer the user's question using ONLY the provided database JSON results.
If the results are empty, clearly state that no data matching their request was found in the system.
CRITICAL RULE: If the database returns multiple rows/entities, you MUST list every single one of them. Do not summarize or leave any entities out.
Do not mention SPARQL, JSON, or GraphDB. Keep the descriptions brief but complete."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "User Question: {question}\n\nDatabase Results:\n{data}"),
    ])

    response = LLMClient.get_instance().invoke_text(
        prompt,
        {
            "question": state["user_question"],
            "data": (
                json.dumps(state["graph_results"], indent=2)
                if state["graph_results"]
                else "EMPTY RESULTS. No data found."
            ),
        },
    )

    state["final_answer"] = response
    return state


# ==============================================================
# 4. ROUTER LOGIC
# ==============================================================


def should_retry(state: ChatState) -> str:
    """Decide whether to retry SPARQL generation or translate."""
    if state.get("error_message") and state["iteration_count"] < 3:
        logger.info("[Router] Error detected -- retrying SPARQL generation.")
        return "retry"
    logger.info("[Router] Success or max retries -- translating results.")
    return "translate"


# ==============================================================
# 5. GRAPH COMPILATION
# ==============================================================


def build_chat_graph() -> StateGraph:
    """
    Assemble and compile the NL-to-SPARQL chat agent.

    Topology
    --------
        ENTRY -> [guardrail]
                   |
                   +-- off-topic --> [customer_service] -> END
                   |
                   +-- valid --> [developer] -> [database]
                                                |
                                       +-------+--------+
                                       | (error & < 3) | (success)
                                       v                v
                                   [developer]    [customer_service] -> END
    """
    workflow = StateGraph(ChatState)

    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("developer", generate_sparql_node)
    workflow.add_node("database", execute_sparql_node)
    workflow.add_node("customer_service", translate_results_node)

    workflow.set_entry_point("guardrail")

    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "developer" if state["is_valid_topic"] else "customer_service",
    )

    workflow.add_edge("developer", "database")

    workflow.add_conditional_edges(
        "database",
        should_retry,
        {
            "retry": "developer",
            "translate": "customer_service",
        },
    )

    workflow.add_edge("customer_service", END)

    return workflow.compile()


# ==============================================================
# 6. PUBLIC ENTRY POINT
# ==============================================================

_schema_cache: str | None = None


def get_schema() -> str:
    """Return the cached live schema, fetching it once."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = fetch_live_schema()
    return _schema_cache


def run_chat_pipeline(question: str) -> dict[str, Any]:
    """
    Execute the full NL-to-SPARQL chat pipeline synchronously.

    Parameters
    ----------
    question : str
        The user's natural-language supply chain question.

    Returns
    -------
    dict
        Final ChatState with keys:
        - final_answer: str -- the NL answer
        - generated_sparql: str -- the SPARQL query used
        - graph_results: list -- raw results from GraphDB
        - is_valid_topic: bool
        - iteration_count: int
    """
    graph = build_chat_graph()
    schema = get_schema()

    initial_state: ChatState = {
        "user_question": question,
        "live_schema": schema,
        "generated_sparql": "",
        "graph_results": [],
        "error_message": "",
        "iteration_count": 0,
        "final_answer": "",
        "is_valid_topic": True,
    }

    final_state: dict[str, Any] = graph.invoke(initial_state)
    return final_state


async def run_chat_pipeline_async(question: str) -> dict[str, Any]:
    """
    Async wrapper for FastAPI endpoints.

    Dispatches the synchronous LangGraph invoke to a thread
    pool so the async event loop is not blocked.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_chat_pipeline, question)
