"""Real API/chain with synthetic evidence and providers; no network or model loading."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import asyncio
import json
import logging
import secrets
import time
from unittest.mock import Mock

import pytest
import httpx
from fastapi.testclient import TestClient
from jose import jwt
from openai import APIConnectionError, RateLimitError

from app import auth, main
from rag import chain, generator, stores
from rag.schema import ENV_JWT_SECRET, TOPIC_LAW, TOPICS, RagRequest
from tests.test_contract import FAKE_DRAFT, FAKE_HIT, FakeLLM, _all_supported


@pytest.fixture
def pipeline(monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv(ENV_JWT_SECRET, secret)
    monkeypatch.setattr(main, "latency_stats", main.LatencyStatistics())
    monkeypatch.setattr(main, "answer", chain.answer)
    monkeypatch.setattr(stores, "get_store", lambda topic: object())
    retrieve = Mock(return_value=[deepcopy(FAKE_HIT)])
    monkeypatch.setattr(chain, "retrieve", retrieve)
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: FakeLLM(deepcopy(FAKE_DRAFT)))
    monkeypatch.setattr(generator, "build_verification_llm", lambda *a, **k: FakeLLM(_all_supported))
    encoded = jwt.encode({"sub": "diagnostic-user", "iss": auth.ISSUER, "exp": int(time.time()) + 600},
                         secret, algorithm=auth.ALGORITHM)
    headers = {"Authorization": "Bearer " + encoded, "Origin": "http://localhost:5174"}
    payload = RagRequest(question="PRIVATE_QUESTION_MARKER", topic=TOPIC_LAW).model_dump()
    yield TestClient(main.app), headers, payload, retrieve, secret


def test_diagnostics_runs_once_and_has_measured_pipeline(pipeline):
    client, headers, payload, retrieve, _ = pipeline
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    data = response.json()
    assert response.status_code == data["http_status"] == 200
    assert data["outcome"] == "answered" and data["failure"] is None
    assert data["response"]["sources"]
    assert retrieve.call_count == 1
    assert response.headers["x-request-id"] == data["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    assert len(response.content) == int(response.headers["content-length"])
    stages = {event["stage"]: event for event in data["trace"]}
    assert {"authentication", "request_dispatch", "preflight", "product_resolution", "retrieval",
            "generation_draft", "evidence_validation", "semantic_verification", "generation_attempt",
            "response_mapping", "equipment_review", "response_ready"} <= stages.keys()
    assert stages["retrieval"]["hit_count"] == 1
    assert stages["generation_draft"]["attempt"] == 1
    assert stages["generation_draft"]["parent_stage"] == "generation_attempt"
    assert data["timing"]["scope"] == "response_ready"
    assert "http_complete" not in stages  # completed sending cannot be in its own body
    assert all(event.get("duration_ms", 0) >= 0 for event in data["trace"])


def test_normal_endpoint_preserves_contract_and_logs_correlated_completion(pipeline, caplog):
    client, headers, payload, _, _ = pipeline
    caplog.set_level(logging.INFO, logger="chembridge.trace")
    response = client.post("/rag-query", json=payload, headers=headers)
    assert set(response.json()) == set(generator.RagResponse.model_fields)
    events = [json.loads(record.getMessage().split(" ", 1)[1]) for record in caplog.records
              if record.name == "chembridge.trace"]
    assert events[-1]["stage"] == "http_complete"
    assert {event["request_id"] for event in events} == {response.headers["x-request-id"]}
    assert main._active_trace.get() is None


def test_held_response_identifies_exact_rule_and_both_attempts(pipeline, monkeypatch):
    client, headers, payload, _, _ = pipeline
    source = "안내표의 색상을 확인한다."
    hit = deepcopy(FAKE_HIT)
    hit["text"] = source
    monkeypatch.setattr(chain, "retrieve", lambda *a, **k: [hit])
    draft = {"supported": True, "statements": [{"kind": "recommendation", "text": "안내표의 색상을 확인해야 해요.",
             "citations": [{"chunk_id": hit["metadata"]["chunk_id"], "quote": source}], "conditions": []}]}
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: FakeLLM(draft))
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    data = response.json()
    assert response.status_code == 200 and data["outcome"] == "held"
    assert data["response"]["sources"] == []
    failure = data["failure"]
    assert failure["stage"] == "review"
    assert failure["reason"] == "invalid_evidence" and failure["check"] == "recommendation_force"
    assert failure["location"]["file"] == "rag/generator.py"
    assert failure["location"]["function"] == "generate_answer"
    assert failure["location"]["line"] > 0
    assert {event["attempt"] for event in data["trace"] if event["stage"] == "generation_attempt"} == set(range(1, generator.GENERATION_RETRIES + 2))


@pytest.mark.parametrize("case, expected, reason", [
    ("missing_token", 401, "authentication_required"),
    ("malformed_json", 422, "malformed_json"),
    ("invalid_field", 422, "invalid_request"),
    ("missing_auth_config", 503, "auth_configuration_unavailable"),
    ("missing_index", 503, "index_unavailable"),
    ("provider_timeout", 503, "llm_timeout"),
    ("verifier_timeout", 503, "verification_unavailable"),
    ("malformed_generation", 503, "invalid_output"),
    ("internal_error", 500, "internal_error"),
])
def test_error_status_and_diagnostic_envelope(pipeline, monkeypatch, case, expected, reason):
    client, headers, payload, retrieve, secret = pipeline
    if case == "missing_token":
        headers.pop("Authorization")
    elif case == "invalid_field":
        payload["topic"] = "invalid"
    elif case == "missing_auth_config":
        monkeypatch.delenv(ENV_JWT_SECRET)
    elif case == "missing_index":
        monkeypatch.setattr(stores, "get_store", lambda topic: None)
    elif case in {"provider_timeout", "verifier_timeout"}:
        class Unavailable:
            def invoke(self, messages):
                raise TimeoutError("PRIVATE_EXCEPTION_MARKER" + secret)
        factory = "build_document_llm" if case == "provider_timeout" else "build_verification_llm"
        monkeypatch.setattr(generator, factory, lambda *a, **k: Unavailable())
    elif case == "malformed_generation":
        monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: FakeLLM({"unexpected": True}))
    elif case == "internal_error":
        def broken(request):
            raise KeyError("PRIVATE_EXCEPTION_MARKER" + secret)
        monkeypatch.setattr(main, "answer", broken)
    response = (client.post(main.DIAGNOSTIC_PATH, content="{", headers={**headers, "Content-Type": "application/json"})
                if case == "malformed_json" else client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers))
    data = response.json()
    assert response.status_code == data["http_status"] == expected
    assert data["outcome"] == "error" and data["failure"]["reason"] == reason
    assert "detail" in data["response"]
    assert data["request_id"] == response.headers["x-request-id"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    assert response.headers["cache-control"] == "no-store"
    assert secret not in response.text and "PRIVATE_EXCEPTION_MARKER" not in response.text
    if expected == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    if case in {"missing_token", "invalid_field", "malformed_json", "missing_auth_config", "missing_index"}:
        retrieve.assert_not_called()


def test_no_hits_is_200_but_emergency_survives_unavailable_index(pipeline, monkeypatch):
    client, headers, payload, retrieve, _ = pipeline
    retrieve.return_value = []
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    assert response.status_code == 200 and response.json()["failure"]["reason"] == "no_evidence"
    monkeypatch.setattr(stores, "get_store", lambda topic: None)
    payload["question"] = "불산이 눈에 들어갔어요"
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    data = response.json()
    assert response.status_code == 200 and data["failure"]["reason"] == "emergency"
    assert "119" in data["response"]["answer"]
    assert next(event for event in data["trace"] if event["stage"] == "retrieval")["status"] == "skipped"
    assert retrieve.call_count == 1


def test_trace_redacts_private_contents_and_isolates_concurrent_requests(pipeline, caplog):
    client, headers, payload, _, secret = pipeline
    caplog.set_level(logging.INFO, logger="chembridge.trace")
    def ask(index):
        return client.post(main.DIAGNOSTIC_PATH + "?token=PRIVATE_QUERY_MARKER", headers=headers,
                           json={**payload, "question": "PRIVATE_QUESTION_MARKER" + str(index)}).json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(ask, range(8)))
    ids = {response["request_id"] for response in responses}
    assert len(ids) == 8
    for response in responses:
        assert response["outcome"] == "answered"
        assert [event["sequence"] for event in response["trace"]] == list(range(1, len(response["trace"]) + 1))
        trace = json.dumps(response["trace"], ensure_ascii=False)
        for private in ("PRIVATE_QUESTION_MARKER", "PRIVATE_QUERY_MARKER", secret, headers["Authorization"], "diagnostic-user"):
            assert private not in trace and private not in caplog.text
    assert main._active_trace.get() is None


def test_health_requires_all_indexes_and_openapi_describes_diagnostics(pipeline, monkeypatch):
    client, _, _, _, _ = pipeline
    monkeypatch.setattr(stores, "status", lambda: {topic: topic == TOPIC_LAW for topic in TOPICS})
    response = client.get("/health")
    assert response.status_code == 503 and response.json()["ready"] is False
    operation = client.get("/openapi.json").json()["paths"][main.DIAGNOSTIC_PATH]["post"]
    assert {"BearerAuth": []} in operation["security"]
    assert {"200", "401", "422", "500", "503"} <= operation["responses"].keys()


@pytest.mark.parametrize("fault", [
    httpx.TimeoutException("private"), httpx.ConnectError("private"),
    APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
    RateLimitError("private", response=httpx.Response(429, request=httpx.Request("POST", "https://example.invalid")), body={}),
])
def test_retrieval_provider_errors_are_503_with_original_stage(pipeline, monkeypatch, fault):
    client, headers, payload, _, _ = pipeline
    monkeypatch.setattr(chain, "retrieve", Mock(side_effect=fault))
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    data = response.json()
    assert response.status_code == 503
    assert data["failure"]["stage"] == "retrieval"
    assert data["failure"]["reason"] == "dependency_unavailable"
    assert data["failure"]["exception_type"] == type(fault).__name__
    assert "private" not in response.text


def test_internal_response_mapping_fault_is_500(pipeline, monkeypatch):
    client, headers, payload, _, _ = pipeline
    monkeypatch.setattr(generator, "build_api_response", Mock(side_effect=ValueError("PRIVATE_MAPPING_DETAILS")))
    response = client.post(main.DIAGNOSTIC_PATH, json=payload, headers=headers)
    assert response.status_code == 500 and response.json()["failure"]["reason"] == "internal_error"
    assert "PRIVATE_MAPPING_DETAILS" not in response.text


def test_request_context_resets_even_if_statistics_fail(monkeypatch):
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message):
        pass

    async def receive():
        return {"type": "http.request", "body": b""}

    monkeypatch.setattr(main.latency_stats, "record", Mock(side_effect=RuntimeError("stats unavailable")))

    async def run():
        with pytest.raises(RuntimeError, match="stats unavailable"):
            await main.RequestLogMiddleware(application)({"type": "http", "path": "/rag-query", "method": "POST"}, receive, send)
        assert main._active_trace.get() is None
    asyncio.run(run())
