# ============================================================
# tests/test_chat_fallback.py
#
# Unit test for chat pipeline behavior during offline/fallback mode.
# ============================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chat_service import run_chat_pipeline
from services.llm_service import LLMClient


def test_chat_offline_fallback():
    print("=" * 60)
    print("TEST: Chat Pipeline Offline Fallback")
    print("=" * 60)

    # Force reset LLM client and initialize it with no API key to force fallback
    import os
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    LLMClient.reset_instance()

    # Call the chat pipeline
    result = run_chat_pipeline("Check if delivery is delayed?")

    print(f"  Final Answer:     {result.get('final_answer')}")
    print(f"  Generated SPARQL: {result.get('generated_sparql')}")
    print(f"  Graph Results:    {result.get('graph_results')}")
    print(f"  Is Valid Topic:   {result.get('is_valid_topic')}")

    # Assertions
    assert "[Fallback Response]" in result["final_answer"], "final_answer should contain the fallback marker"
    assert "[Fallback Response]" in result["generated_sparql"], "generated_sparql should contain the fallback marker"
    assert len(result["graph_results"]) == 0, "graph_results should be empty"
    assert result["is_valid_topic"] is True, "is_valid_topic should be True under fallback logic"

    print("  [PASS] Offline fallback test passed successfully!")


if __name__ == "__main__":
    test_chat_offline_fallback()
