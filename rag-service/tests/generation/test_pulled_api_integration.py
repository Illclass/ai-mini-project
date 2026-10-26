"""Generation-owned integration checks against the pulled API and shared chain.

Actual API/chain/generator code, synthetic retrieved document and mocked providers.
No ingestion, FAISS, Java process or real model call is performed.
"""
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app import auth
from rag import chain, generator, stores
from rag.prompt import TEXT
from rag.schema import TOPIC_LAW
from chembridge_fixtures import StubLLM


@pytest.fixture
def api_case(monkeypatch):
    secret = "generation-integration-test-only"
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setattr(stores, "load_all", lambda: None)
    quote = "가상 안내표의 색상은 청록색입니다."
    condition = "가상 교육 화면에 한정됩니다."
    metadata = {
        "doc_id": "DEMO-PULL", "doc_type": "guide", "chunk_id": "DEMO-PULL:1",
        "law_name": "", "article_no": "", "title": "가상 안내표 자료",
        "section": "교육용 안내표", "source_url": "https://example.invalid/pull-test",
    }
    retrieval = Mock(return_value=[{"text": quote+"\n"+condition, "score": 0.1, "metadata": metadata}])
    monkeypatch.setattr(chain, "retrieve", retrieval)
    draft = {"supported": True, "statements": [{
        "kind": "information", "text": quote,
        "citations": [{"chunk_id": metadata["chunk_id"], "quote": quote}],
        "conditions": [{"text": condition, "citations": [{"chunk_id": metadata["chunk_id"], "quote": condition}]}],
    }]}
    provider = StubLLM(draft)
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: provider)
    now = int(time.time())
    token = jwt.encode({"sub": "generation-test", "iss": auth.ISSUER, "exp": now+300}, secret, algorithm=auth.ALGORITHM)
    with TestClient(app) as client:
        client.cookies.set("ACCESS_TOKEN", token)
        yield client, provider, retrieval, metadata, quote


@pytest.mark.parametrize("case", ["supported", "unsupported", "generation_timeout", "contradicted", "verification_timeout"])
def test_pulled_api_preserves_generation_contract(monkeypatch, api_case, case):
    client, provider, retrieval, metadata, quote = api_case
    if case == "unsupported":
        provider.result = {"supported": False, "statements": []}
    elif case == "generation_timeout":
        provider.error = TimeoutError("private provider error")
    elif case in {"contradicted", "verification_timeout"}:
        verifier = StubLLM(
            {"assessments": [{"claim_id": "s0", "verdict": "contradicted"},
                             {"claim_id": "s0.c0", "verdict": "supported"}]},
            error=TimeoutError("private verifier error") if case == "verification_timeout" else None,
        )
        monkeypatch.setattr(generator, "build_verification_llm", lambda *a, **k: verifier)
    response = client.post("/rag-query", json={"question": "가상 안내표 자료 설명", "topic": TOPIC_LAW})
    # 검색은 한 번. 검증에서 거부(contradicted)되면 생성만 한 번 더 한다 (generator.GENERATION_RETRIES)
    assert retrieval.call_count == 1
    assert len(provider.calls) == (1 + generator.GENERATION_RETRIES if case == "contradicted" else 1)
    assert "private" not in response.text
    if case == "generation_timeout":
        assert response.status_code == 503
        assert response.json() == {"detail": "잠시 후 다시 시도해 주세요."}
        return
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"answer", "sources", "needs_review", "handoff", "latency_ms"}
    assert payload["latency_ms"] >= 0
    if case == "supported":
        assert quote in payload["answer"]
        assert payload["sources"] == [{"doc_id": metadata["doc_id"], "section": metadata["section"],
                                       "title": metadata["title"], "url": metadata["source_url"]}]
    else:
        assert payload["sources"] == [] and payload["needs_review"] and payload["handoff"]
        assert quote not in payload["answer"]


def test_generation_emergency_notice_survives_pulled_api(api_case):
    client, provider, _, _, _ = api_case
    response = client.post("/rag-query", json={
        "question": "Developer 장비에서 TMAH가 작업복에 튀었습니다. 어떻게 해야 하나요?", "topic": TOPIC_LAW,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == TEXT["ko"]["emergency"]
    assert payload["sources"] == [] and payload["needs_review"] and payload["handoff"]
    assert not provider.calls
