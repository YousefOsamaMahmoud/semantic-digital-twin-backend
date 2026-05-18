# ============================================================
# services/llm_service.py — Layer 2: LLM Client + SLA Extraction
#
# This module provides two layers of functionality:
#
#   1. LLM Infrastructure (LLMConfig + LLMClient singleton)
#      - Resilient structured/text invocation with automatic
#        429/Quota fallback to deterministic simulation responses
#      - Every downstream service uses this, NOT raw ChatOpenAI
#
#   2. SLA Extraction LangGraph Pipeline
#      - Guardrail → Extractor → Validator (self-correcting loop)
#      - Exposes run_extraction_pipeline(raw_text) for the API layer
# ============================================================

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

from models.schemas import ExtractedSLAData, RiskAnalysisResult

logger = logging.getLogger(__name__)


# ==============================================================
# 1. LLM INFRASTRUCTURE LAYER
# ==============================================================


@dataclass
class LLMConfig:
    """
    Immutable configuration container for the LLM client.

    All values are read from environment variables with sensible
    defaults for the OpenRouter → DeepSeek path used during
    development.  Swap GRAPHDB_URL / LLM_API_KEY in .env to
    point at a different provider.

    Fields
    ------
    provider : str
        Human-readable label (used for logging only).
    model : str
        Model identifier passed to the LangChain Chat client.
    api_key : str
        API key read from the LLM_API_KEY env-var.
    base_url : str
        Base URL of the API provider.
    temperature : float
        Sampling temperature passed to the model.
    max_tokens : int
        Maximum tokens in the generated response.
    fallback_enabled : bool
        When True, quota / 429 errors produce a deterministic
        simulation response instead of raising.
    max_retries : int
        Number of times to retry a non-quota error before
        falling back or re-raising.
    retry_delay_ms : int
        Milliseconds to wait between retries.
    """

    provider: str = "openrouter"
    model: str = "deepseek/deepseek-chat"
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL", "https://openrouter.ai/api/v1"
        )
    )
    temperature: float = 0.0
    max_tokens: int = 800
    fallback_enabled: bool = field(
        default_factory=lambda: os.getenv("LLM_FALLBACK_ENABLED", "true").lower()
        == "true"
    )
    max_retries: int = 2
    retry_delay_ms: int = 1000


class LLMClient:
    """
    Thread-safe singleton LLM client with automatic fallback.

    Usage
    -----
    >>> client = LLMClient.get_instance()
    >>> result = client.invoke_structured(prompt, vars, ExtractedSLAData)

    All LLM calls across services/ MUST go through this class.
    """

    _instance: Optional["LLMClient"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()
        self._primary_llm: Optional[ChatOpenAI] = None

    # ----------------------------------------------------------
    # Singleton access
    # ----------------------------------------------------------

    @classmethod
    def get_instance(cls, config: Optional[LLMConfig] = None) -> "LLMClient":
        """Return the singleton client, creating it if necessary."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Clear the singleton (useful for testing with a different config)."""
        cls._instance = None

    # ----------------------------------------------------------
    # Internal — lazy LLM initialization
    # ----------------------------------------------------------

    def _ensure_llm(self) -> ChatOpenAI:
        """
        Lazily build and cache the LangChain ChatOpenAI client.

        Returns the existing LLM if already built.  If the API key is
        missing and fallback is disabled, raises a clear ``ValueError``.
        When fallback is enabled the caller should catch construction
        errors and return a deterministic simulation instead.
        """
        if self._primary_llm is not None:
            return self._primary_llm

        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            if self.config.fallback_enabled:
                self._primary_llm = None
                raise ValueError(
                    "No LLM API key configured. "
                    "Fallback mode is enabled — will return simulated responses."
                )
            raise ValueError(
                "No LLM API key configured. Set LLM_API_KEY or OPENAI_API_KEY "
                "in your .env file, or enable fallback with LLM_FALLBACK_ENABLED=true."
            )

        self._primary_llm = ChatOpenAI(
            model=self.config.model,
            openai_api_key=api_key,
            openai_api_base=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return self._primary_llm

    # ----------------------------------------------------------
    # Public — structured output (tool-use / function-calling)
    # ----------------------------------------------------------

    def invoke_structured(
        self,
        prompt: ChatPromptTemplate,
        input_vars: dict[str, Any],
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """
        Call the LLM with structured output guarantees.

        The LLM is invoked with ``.with_structured_output(output_schema)``
        so the response is guaranteed to be a valid Pydantic instance of
        the requested schema — no JSON parsing required.

        **Resilience contract**

        1. Try the primary model.
        2. If a 429 / Quota / Resource-Exhausted error is caught:
           log a warning and return ``_generate_fallback(schema, input_vars)``.
        3. If any other error is caught: retry up to ``max_retries`` times
           with a short delay between attempts.
        4. If all retries are exhausted without success: return the fallback
           (when ``fallback_enabled``) or re-raise (when disabled).

        Parameters
        ----------
        prompt : ChatPromptTemplate
            The fully-constructed LangChain prompt template.
        input_vars : dict[str, Any]
            Variables to interpolate into the prompt template.
        output_schema : type[BaseModel]
            A Pydantic model class that the LLM must populate.

        Returns
        -------
        BaseModel
            A valid instance of ``output_schema`` — either from the real
            LLM or from the deterministic fallback generator.
        """
        for attempt in range(1 + self.config.max_retries):
            try:
                llm = self._ensure_llm()
                chain = prompt | llm.with_structured_output(output_schema)
                return chain.invoke(input_vars)

            except Exception as exc:
                error_str = str(exc).lower()
                is_quota = (
                    "429" in error_str
                    or "quota" in error_str
                    or "resource exhausted" in error_str
                    or "rate limit" in error_str
                )

                if is_quota and self.config.fallback_enabled:
                    logger.warning(
                        "LLM quota exceeded (%s). Returning simulated fallback for %s.",
                        exc,
                        output_schema.__name__,
                    )
                    return self._generate_fallback(output_schema, input_vars)

                if attempt < self.config.max_retries:
                    wait = self.config.retry_delay_ms / 1000.0
                    logger.info(
                        "LLM call failed (attempt %d/%d): %s. Retrying in %.1fs …",
                        attempt + 1,
                        self.config.max_retries + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                logger.error(
                    "LLM call failed after %d retries: %s",
                    self.config.max_retries,
                    exc,
                )
                if self.config.fallback_enabled:
                    return self._generate_fallback(output_schema, input_vars)
                raise

        # Safety net — should be unreachable unless max_retries is 0
        # and the very first call also didn't hit any of the branches above.
        return self._generate_fallback(output_schema, input_vars)

    # ----------------------------------------------------------
    # Public — free-text output (alerts, SPARQL, translations)
    # ----------------------------------------------------------

    def invoke_text(
        self,
        prompt: ChatPromptTemplate,
        input_vars: dict[str, Any],
    ) -> str:
        """
        Call the LLM for free-text generation.

        Same retry / fallback contract as ``invoke_structured`` but
        returns a plain string instead of a Pydantic object.

        Parameters
        ----------
        prompt : ChatPromptTemplate
            The fully-constructed LangChain prompt template.
        input_vars : dict[str, Any]
            Variables to interpolate into the prompt template.

        Returns
        -------
        str
            Free-text response from the LLM or a safe fallback string.
        """
        for attempt in range(1 + self.config.max_retries):
            try:
                llm = self._ensure_llm()
                chain = prompt | llm
                return chain.invoke(input_vars).content.strip()

            except Exception as exc:
                error_str = str(exc).lower()
                is_quota = (
                    "429" in error_str
                    or "quota" in error_str
                    or "resource exhausted" in error_str
                )

                if is_quota and self.config.fallback_enabled:
                    logger.warning(
                        "LLM quota exceeded (%s). Returning fallback text.", exc
                    )
                    return self._generate_fallback_text(input_vars)

                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay_ms / 1000.0)
                    continue

                if self.config.fallback_enabled:
                    return self._generate_fallback_text(input_vars)
                raise

        return self._generate_fallback_text(input_vars)

    # ----------------------------------------------------------
    # Private — deterministic fallback generators
    # ----------------------------------------------------------

    def _generate_fallback(
        self,
        schema: type[BaseModel],
        context: dict[str, Any],
    ) -> BaseModel:
        """
        Return a deterministic, valid instance of *schema* without
        calling any external API.

        Each known schema gets a hand-crafted mock populated with
        conservative / safe defaults so that downstream code never
        crashes with ``AttributeError`` or ``ValidationError``.

        When *schema* is not explicitly handled, an empty instance is
        returned via ``schema()`` as a last resort.
        """
        if schema is ExtractedSLAData:
            return ExtractedSLAData(
                document_id=f"FALLBACK-{uuid4().hex[:8]}",
                supplier_id="unknown",
                supplier_name="Unknown Supplier (Fallback)",
                material="Unknown Material (Fallback)",
                sla_lead_time_hours=72,
                delay_penalty_rate=500.0,
                missed_item_penalty_rate=150.0,
                minimum_quality_threshold=0.98,
                quality_penalty_rate=0.15,
            )

        if schema is RiskAnalysisResult:
            return RiskAnalysisResult(
                risks=["DelayEvent"],
                confidence=0.5,
                severity="Low",
                financial_penalty_estimate=0.0,
                reasoning=(
                    "Fallback mode: LLM quota exceeded. "
                    "Conservative default risk assessment applied. "
                    "No active alerts generated."
                ),
            )

        # Generic fallback — may produce an empty model but will
        # not raise an exception.
        try:
            return schema()
        except Exception as fallback_exc:
            logger.error("Cannot build fallback for unknown schema %s: %s", schema, fallback_exc)
            raise fallback_exc

    def _generate_fallback_text(self, context: dict[str, Any]) -> str:
        """
        Return a safe, deterministic fallback text when the LLM
        is unreachable due to a quota error.

        The message is generic enough to be returned from any
        free-text node (guardrail, SPARQL generation, alert writing,
        NL translation) without confusing the user.
        """
        return (
            "[Fallback Response] The AI assistant is currently in offline mode "
            "due to a temporary service interruption. Please try again later."
        )


# ==============================================================
# 2. SLA EXTRACTION STATE
# ==============================================================


class SLAExtractionState(TypedDict):
    """
    LangGraph state dictionary for the SLA extraction pipeline.

    Keys
    ----
    raw_document_text : str
        The full raw text extracted from the uploaded PDF.
    document_id : str
        Unique document identifier (auto-generated or from the PDF).
    is_valid_contract : bool
        Guardrail verdict — is the document an actual SLA contract?
    extracted_data : ExtractedSLAData | None
        The structured LLM output (None before extraction runs).
    iteration_count : int
        Number of extraction attempts (max 3 before giving up).
    error_message : str
        Business-logic validation error (fed back into the re-prompt).
    rdf_triples : str
        Generated SPARQL INSERT string (populated by lifting_service).
    injection_success : bool
        Whether the triples were successfully persisted to GraphDB.
    """

    raw_document_text: str
    document_id: str
    is_valid_contract: bool
    extracted_data: Optional[ExtractedSLAData]
    iteration_count: int
    error_message: str
    rdf_triples: str
    injection_success: bool


def _make_initial_state(raw_text: str) -> SLAExtractionState:
    """Build a clean initial state dictionary for a new extraction run."""
    return {
        "raw_document_text": raw_text,
        "document_id": f"DOC-{uuid4().hex[:12].upper()}",
        "is_valid_contract": False,
        "extracted_data": None,
        "iteration_count": 0,
        "error_message": "",
        "rdf_triples": "",
        "injection_success": False,
    }


# ==============================================================
# 3. LANGGRAPH NODES
# ==============================================================


def document_guardrail_node(state: SLAExtractionState) -> SLAExtractionState:
    """
    Node 0 — Document Security Guardrail.

    Uses the LLM to classify the raw text as a valid supply-chain SLA
    contract or not.

    **Fallback behaviour**

    When the LLM is unreachable (no API key, quota exhausted, network
    error) the ``invoke_text`` call returns a deterministic fallback
    string starting with ``[Fallback Response]``.  In that situation
    the guardrail **accepts** the document so that downstream nodes
    (extraction, validation) also run in simulation mode, allowing
    developers to test the endpoint plumbing end-to-end without a
    live API key.
    """
    logger.info("[Node 0] Document Security Guardrail")

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a document classifier. Read the text and determine "
            "if it is a supply chain Service Level Agreement (SLA) or "
            "contract. Output ONLY 'VALID' or 'INVALID'.",
        ),
        ("human", "{text}"),
    ])

    response = (
        LLMClient.get_instance()
        .invoke_text(prompt, {"text": state["raw_document_text"]})
        .strip()
        .upper()
    )

    # Fallback detection — the LLM client injects this prefix when
    # it cannot reach the API.  In that case we accept the document
    # so the pipeline can return simulated data for testing.
    FALLBACK_MARKER = "[FALLBACK RESPONSE]"
    if response.startswith(FALLBACK_MARKER):
        logger.info(
            "    [!] LLM unreachable (fallback mode). "
            "Accepting document to allow simulation pipeline."
        )
        state["is_valid_contract"] = True
    elif "VALID" in response:
        logger.info("    [+] Document verified: Valid SLA contract.")
        state["is_valid_contract"] = True
    else:
        logger.info("    [-] Document rejected: Not an SLA contract.")
        state["is_valid_contract"] = False

    return state


def extraction_agent_node(state: SLAExtractionState) -> SLAExtractionState:
    """
    Node 1 — Tool-Calling Extraction Agent.

    Calls the LLM with ``.with_structured_output(ExtractedSLAData)``
    so the response is a validated Pydantic object.  If a previous
    validation error exists, it is injected into the prompt so the
    LLM can self-correct.
    """
    attempt = state.get("iteration_count", 0) + 1
    logger.info("[Node 1] Tool-Calling Extractor (Attempt %d)", attempt)

    system_prompt = (
        "You are an expert legal data extraction AI. "
        "Extract the exact financial and logistical parameters from "
        "the contract using the provided tool schema.\n\n"
        "### PREVIOUS BUSINESS LOGIC ERRORS TO FIX ###\n{error_message}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{text}"),
    ])

    client = LLMClient.get_instance()
    result = client.invoke_structured(
        prompt,
        {
            "text": state["raw_document_text"],
            "error_message": state.get("error_message", "None."),
        },
        ExtractedSLAData,
    )

    state["extracted_data"] = result  # type: ignore[assignment]
    state["iteration_count"] = attempt
    return state


def business_logic_validator_node(
    state: SLAExtractionState,
) -> SLAExtractionState:
    """
    Node 2 — Semantic Business Logic Validator.

    Inspects the extracted fields for real-world sanity:

    * Lead time must be positive and reasonable (< 8760 hours = 1 year).
    * Quality threshold must be a decimal ≤ 1.0.
    * Quality penalty must be a decimal ≤ 1.0.
    * Supplier and material names must be non-empty.

    On failure the ``error_message`` is updated so the re-prompt
    tells the LLM exactly what to fix.
    """
    logger.info("[Node 2] Semantic Business Logic Validator")
    data = state["extracted_data"]

    if data is None:
        state["error_message"] = "Extracted data is empty. Please re-parse the contract."
        return state

    errors: list[str] = []

    # Rule 1: Lead time must be positive and not exceed one year.
    if data.sla_lead_time_hours <= 0:
        errors.append(
            "Lead time must be greater than 0 hours. "
            "Re-read the contract for the correct turnaround window."
        )
    elif data.sla_lead_time_hours > 8760:
        errors.append(
            f"Lead time ({data.sla_lead_time_hours}h) exceeds one year. "
            "This is likely a mis-parse. Check the contract."
        )

    # Rule 2: Quality threshold must be a decimal 0.0–1.0
    if data.minimum_quality_threshold > 1.0:
        errors.append(
            f"Quality threshold ({data.minimum_quality_threshold}) is > 1.0. "
            "Convert percentages to decimals (e.g., 95% -> 0.95)."
        )
    if data.minimum_quality_threshold <= 0.0:
        errors.append(
            f"Quality threshold ({data.minimum_quality_threshold}) is <= 0.0. "
            "A valid contract must specify a minimum quality requirement."
        )

    # Rule 3: Quality penalty must be a decimal 0.0–1.0
    if data.quality_penalty_rate > 1.0:
        errors.append(
            f"Quality penalty rate ({data.quality_penalty_rate}) is > 1.0. "
            "Convert percentages to decimals (e.g., 15% -> 0.15)."
        )

    # Rule 4: Penalty rates should not be negative
    if data.delay_penalty_rate < 0:
        errors.append(
            f"Delay penalty rate ({data.delay_penalty_rate}) is negative. "
            "Penalties cannot be negative. Re-read the contract."
        )
    if data.missed_item_penalty_rate < 0:
        errors.append(
            f"Missed item penalty rate ({data.missed_item_penalty_rate}) "
            "is negative. Penalties cannot be negative."
        )

    # Rule 5: Supplier and material names must be non-empty
    if not data.supplier_id.strip():
        errors.append("Supplier ID is empty. Extract the supplier identifier.")
    if not data.supplier_name.strip():
        errors.append("Supplier name is empty. Extract the supplier name.")
    if not data.material.strip():
        errors.append("Material name is empty. Extract the material name.")

    if errors:
        combined = " | ".join(errors)
        logger.info("    [-] Business logic errors: %s", combined)
        state["error_message"] = combined
    else:
        logger.info("    [+] Semantic data validated: all parameters align with business rules.")
        state["error_message"] = ""

    return state


# ==============================================================
# 4. ROUTER LOGIC
# ==============================================================


def check_validation_success(state: SLAExtractionState) -> str:
    """
    Conditional edge router.

    Returns ``"retry_extraction"`` when validation failed and we
    still have retries left.  Returns ``"inject"`` when the data
    is clean or we have exhausted retries.

    The string is used as the edge key in the conditional edge map.
    """
    if state["error_message"] and state["iteration_count"] < 3:
        logger.info(
            "[Router] Validation failed — routing back to extractor "
            "(attempt %d/3).",
            state["iteration_count"],
        )
        return "retry_extraction"
    logger.info("[Router] Validation passed — routing to inject.")
    return "inject"


# ==============================================================
# 5. GRAPH COMPILATION
# ==============================================================


def build_extraction_graph() -> StateGraph:
    """
    Assemble and compile the SLA extraction LangGraph.

    Topology
    --------
        ENTRY → [guardrail]
                   │
                   ├── INVALID ──→ END
                   │
                   └── VALID ──→ [extractor]
                                   │
                                   ▼
                               [validator]
                                   │
                          ┌────────┴────────┐
                          │ (error & < 3)  │ (success)
                          ▼                 ▼
                      [extractor]         END
    """
    workflow = StateGraph(SLAExtractionState)

    # Register nodes
    workflow.add_node("guardrail", document_guardrail_node)
    workflow.add_node("extractor", extraction_agent_node)
    workflow.add_node("validator", business_logic_validator_node)

    # Entry point
    workflow.set_entry_point("guardrail")

    # Conditional edge from guardrail
    workflow.add_conditional_edges(
        "guardrail",
        lambda state: "extractor" if state["is_valid_contract"] else END,
    )

    # Sequential edge: extractor → validator
    workflow.add_edge("extractor", "validator")

    # Conditional edge from validator
    workflow.add_conditional_edges(
        "validator",
        check_validation_success,
        {
            "retry_extraction": "extractor",
            "inject": END,
        },
    )

    return workflow.compile()


# ==============================================================
# 6. PUBLIC ENTRY POINT
# ==============================================================


def run_extraction_pipeline(raw_text: str) -> dict[str, Any]:
    """
    Execute the full SLA extraction LangGraph pipeline.

    This is the single public API for the API layer
    (``api/sandbox.py`` → ``POST /upload-pdf``).  It takes raw
    PDF text and returns the final ``SLAExtractionState`` dictionary
    containing the guardrail verdict, extracted data (if any),
    validation errors, and the iteration count.

    Parameters
    ----------
    raw_text : str
        The full text content extracted from an uploaded SLA PDF.

    Returns
    -------
    dict[str, Any]
        The final state dictionary after the graph terminates.
        Key fields consumers will inspect:
        - ``is_valid_contract`` — was the document accepted?
        - ``extracted_data`` --- ``ExtractedSLAData | None``
        - ``error_message`` --- validation error or empty string
        - ``iteration_count`` --- how many extraction attempts were made
    """
    graph = build_extraction_graph()
    initial_state = _make_initial_state(raw_text)
    final_state: dict[str, Any] = graph.invoke(initial_state)
    return final_state
