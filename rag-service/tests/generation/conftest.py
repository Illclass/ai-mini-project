"""Generation test scope only: resolve rag package without importing the API."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def pytest_configure(config):
    config.addinivalue_line("markers", "claim_verifier: explicit verifier injection/factory checks; no blanket supported mock")
    config.addinivalue_line("markers", "live: opt-in real LLM calls with synthetic documents (billable)")


# Existing unit tests isolate generation/local validation. Semantic judgement is
# explicitly mocked here; it must never silently trigger a real provider call.
import json
import pytest


@pytest.fixture(autouse=True)
def supported_verifier_for_existing_unit_tests(monkeypatch, request):
    if request.node.get_closest_marker("live") or request.node.get_closest_marker("claim_verifier"):
        return
    from rag import generator

    class SupportedVerifier:
        def invoke(self, messages):
            data = json.loads(messages[1].content.split("\n", 1)[1])
            return {"assessments": [{"claim_id": c["claim_id"], "verdict": "supported"}
                                    for c in data["claims"]]}

    monkeypatch.setattr(generator, "build_verification_llm", lambda *a, **k: SupportedVerifier())
