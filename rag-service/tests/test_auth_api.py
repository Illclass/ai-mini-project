"""인증 연동·CORS·로그 회귀 테스트. 외부 서비스 호출 없이 검증한다."""
import logging
import secrets
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import auth, main
from rag.schema import DOC_TYPE_LAW, ENV_JWT_SECRET, LANGUAGES, TOPIC_LAW, TOPICS, RagRequest, RagResponse, make_chunk_id


@pytest.fixture
def api(monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv(ENV_JWT_SECRET, secret)
    monkeypatch.setattr(main, "answer", lambda req: RagResponse(answer="테스트 안내"))
    client = TestClient(main.app)
    yield client, secret
    main.app.dependency_overrides.clear()


def token(secret, **changes):
    claims = {"sub": "1", "username": "tester", "iss": auth.ISSUER, "exp": int(time.time()) + 600}
    claims.update(changes)
    return jwt.encode(claims, secret, algorithm=auth.ALGORITHM)


def body():
    return RagRequest(question="PRIVATE_QUESTION_MARKER", topic=TOPIC_LAW).model_dump()


def app_logs(caplog):
    return "\n".join(record.getMessage() for record in caplog.records
                     if record.name in ("chembridge.requests", "app.main", "root"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_bearer_without_cookie(api, language):
    client, secret = api
    response = client.post("/rag-query", headers={"Authorization": "Bearer " + token(secret)},
                           json={**body(), "language": language})
    assert response.status_code == 200
    RagResponse.model_validate(response.json())


def test_existing_cookie_is_compatible(api):
    client, secret = api
    client.cookies.set("ACCESS_TOKEN", token(secret))
    assert client.post("/rag-query", json=body()).status_code == 200


@pytest.mark.parametrize("authorization", ["", "Basic value", "Bearer", "Bearer invalid", "Bearer bad token"])
def test_invalid_bearer_cannot_fall_back_to_cookie(api, authorization):
    client, secret = api
    client.cookies.set("ACCESS_TOKEN", token(secret))
    response = client.post("/rag-query", headers={"Authorization": authorization}, json=body())
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_valid_bearer_takes_priority_over_forged_cookie(api):
    client, secret = api
    client.cookies.set("ACCESS_TOKEN", "invalid")
    response = client.post("/rag-query", headers={"Authorization": "Bearer " + token(secret)}, json=body())
    assert response.status_code == 200


@pytest.mark.parametrize("changes", [
    {"exp": 0}, {"exp": None}, {"exp": []}, {"exp": "invalid"},
    {"sub": ""}, {"sub": 1}, {"iss": "wrong-issuer"},
])
def test_bad_bearer_claims_are_401(api, changes):
    client, secret = api
    response = client.post("/rag-query", headers={"Authorization": "Bearer " + token(secret, **changes)}, json=body())
    assert response.status_code == 401


@pytest.mark.parametrize("missing", ["exp", "sub", "iss"])
def test_required_bearer_claims(api, missing):
    client, secret = api
    claims = jwt.get_unverified_claims(token(secret))
    claims.pop(missing)
    encoded = jwt.encode(claims, secret, algorithm=auth.ALGORITHM)
    assert client.post("/rag-query", headers={"Authorization": "Bearer " + encoded}, json=body()).status_code == 401


def test_forged_bearer_is_401(api):
    client, _ = api
    encoded = token(secrets.token_urlsafe(32))
    assert client.post("/rag-query", headers={"Authorization": "Bearer " + encoded}, json=body()).status_code == 401


def test_missing_token_is_401(api):
    client, _ = api
    assert client.post("/rag-query", json=body()).status_code == 401


def test_missing_secret_is_503(api, monkeypatch):
    client, secret = api
    monkeypatch.delenv(ENV_JWT_SECRET)
    assert client.post("/rag-query", headers={"Authorization": "Bearer " + token(secret)}, json=body()).status_code == 503


def test_cors_preflight_accepts_authorization(api):
    client, _ = api
    response = client.options("/rag-query", headers={
        "Origin": "http://localhost:5174", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_cors_disallows_other_origins(api):
    client, _ = api
    response = client.options("/rag-query", headers={
        "Origin": "http://untrusted.invalid", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("case, expected", [("ok", 200), ("unauthenticated", 401), ("invalid", 422), ("upstream", 503)])
def test_error_cors_and_private_logs(api, monkeypatch, caplog, case, expected):
    client, secret = api
    encoded = token(secret)
    headers = {"Origin": "http://localhost:5174", "Authorization": "Bearer " + encoded}
    payload = body()
    caplog.set_level(logging.INFO)
    if case == "unauthenticated":
        headers.pop("Authorization")
    elif case == "invalid":
        payload["topic"] = "invalid"
    elif case == "upstream":
        def fail(req):
            raise TimeoutError(req.question + encoded + secret)
        monkeypatch.setattr(main, "answer", fail)
    response = client.post("/rag-query?token=PRIVATE_QUERY_MARKER", json=payload, headers=headers)
    assert response.status_code == expected
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    logs = app_logs(caplog)
    assert f"path=/rag-query status={expected} latency_ms=" in logs
    for private in ("PRIVATE_QUESTION_MARKER", "PRIVATE_QUERY_MARKER", encoded, secret):
        assert private not in logs


def test_unexpected_error_preserves_cors_and_privacy(api, caplog):
    client, secret = api
    caplog.set_level(logging.INFO)
    def fail():
        raise RuntimeError("PRIVATE_QUESTION_MARKER" + secret)
    main.app.dependency_overrides[auth.get_current_user] = fail
    response = client.post("/rag-query", json=body(), headers={"Origin": "http://localhost:5174"})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    assert "PRIVATE_QUESTION_MARKER" not in app_logs(caplog)
    assert secret not in app_logs(caplog)


def test_swagger_documents_bearer(api):
    client, _ = api
    schema = client.get("/openapi.json").json()
    scheme = schema["components"]["securitySchemes"]["BearerAuth"]
    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    operation = schema["paths"]["/rag-query"]["post"]
    assert {"BearerAuth": []} in operation["security"]
    assert {"200", "401", "422", "503"} <= operation["responses"].keys()


def test_index_startup_failure_keeps_health_available(monkeypatch, caplog):
    def fail():
        raise RuntimeError("PRIVATE_STARTUP_MARKER")
    monkeypatch.setattr(main.stores, "load_all", fail)
    monkeypatch.setattr(main.stores, "is_ready", lambda: False)
    monkeypatch.setattr(main.stores, "status", lambda: {topic: False for topic in TOPICS})
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/docs").status_code == 200
    assert "PRIVATE_STARTUP_MARKER" not in caplog.text


@pytest.mark.parametrize("case, expected", [
    ("missing_token", 401), ("expired_token", 401), ("invalid_topic", 422),
    ("invalid_language", 422), ("too_short", 422), ("too_long", 422), ("malformed_json", 422),
])
def test_rejected_request_never_calls_chain(api, monkeypatch, case, expected):
    client, secret = api
    monkeypatch.setattr(main, "answer", lambda req: pytest.fail("거부된 요청에서 chain을 호출했습니다"))
    headers = {"Authorization": "Bearer " + token(secret)}
    payload = body()
    if case == "missing_token":
        headers.clear()
    elif case == "expired_token":
        headers["Authorization"] = "Bearer " + token(secret, exp=0)
    elif case == "invalid_topic":
        payload["topic"] = "invalid"
    elif case == "invalid_language":
        payload["language"] = "unsupported"
    elif case == "too_short":
        payload["question"] = "a"
    elif case == "too_long":
        payload["question"] = "a" * 501
    if case == "malformed_json":
        response = client.post("/rag-query", content="{", headers={**headers, "Content-Type": "application/json"})
    else:
        response = client.post("/rag-query", json=payload, headers=headers)
    assert response.status_code == expected


@pytest.mark.parametrize("failure", [TimeoutError, ConnectionError, RuntimeError])
def test_chain_errors_are_sanitized_503(api, monkeypatch, failure):
    client, secret = api
    def fail(req):
        raise failure("PRIVATE_UPSTREAM_DETAILS_" + req.question + secret)
    monkeypatch.setattr(main, "answer", fail)
    response = client.post("/rag-query", json=body(), headers={"Authorization": "Bearer " + token(secret)})
    assert response.status_code == 503
    assert response.json() == {"detail": "잠시 후 다시 시도해 주세요."}


@pytest.mark.parametrize("ready, expected", [(True, 200), (False, 503)])
def test_health_readiness_status(api, monkeypatch, ready, expected):
    client, _ = api
    monkeypatch.setattr(main.stores, "is_ready", lambda: ready)
    monkeypatch.setattr(main.stores, "status", lambda: {topic: ready for topic in TOPICS})
    response = client.get("/health")
    assert response.status_code == expected
    assert response.json() == {"ready": ready, "indexes": {topic: ready for topic in TOPICS}}


def test_unmatched_path_does_not_leak_user_input(api, caplog):
    client, _ = api
    caplog.set_level(logging.INFO)
    response = client.get("/PRIVATE_PATH_MARKER?secret=PRIVATE_QUERY_MARKER",
                          headers={"Origin": "http://localhost:5174"})
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    logs = app_logs(caplog)
    assert "path=/unmatched status=404 latency_ms=" in logs
    assert "PRIVATE_PATH_MARKER" not in logs and "PRIVATE_QUERY_MARKER" not in logs


def test_wrong_method_is_405_with_cors(api):
    client, _ = api
    response = client.get("/rag-query", headers={"Origin": "http://localhost:5174"})
    assert response.status_code == 405
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


@pytest.mark.parametrize("doc_id", ["FIXTURE-LAW", "", None])
def test_api_preserves_sources_and_exposes_generation_metadata_hold(api, monkeypatch, doc_id):
    """API는 출처를 제거하지 않는다. 구 청크의 빈 doc_id는 생성 단계에서 보류한다.

    검색·LLM은 격리하고 실제 chain→generate→응답 직렬화를 연결해 병합 회귀를 확인한다.
    """
    from rag import chain, generator

    client, secret = api
    metadata = {
        "doc_id": doc_id, "doc_type": DOC_TYPE_LAW, "topic": TOPIC_LAW,
        "chunk_id": make_chunk_id("FIXTURE-LAW", "1"),
        "title": "가상 테스트 법령", "section": "제1조", "law_name": "가상 테스트 법령",
        "article_no": "제1조", "source_url": "https://example.invalid/fixture",
    }
    if doc_id is None:
        metadata.pop("doc_id")
    hits = [{"text": "실제 법령이 아닌 API 전송 검증용 자료입니다.", "score": 0.0, "metadata": metadata}]
    calls = []

    def generated_result(question, documents, **kwargs):
        calls.append(documents)
        return generator.GenerationOutput(
            answer="출처 전송 확인용 테스트 응답",
            sources=[generator.SourceMetadata.model_validate(documents[0].metadata)],
            needs_review=False, handoff=False,
        )

    monkeypatch.setattr(main, "answer", chain.answer)
    monkeypatch.setattr(chain, "retrieve", lambda *args, **kwargs: hits)
    monkeypatch.setattr(generator, "generate_answer", generated_result)
    response = client.post("/rag-query", json=RagRequest(
        question="중대재해법의 기준은?", topic=TOPIC_LAW,
    ).model_dump(), headers={"Authorization": "Bearer " + token(secret)})
    assert response.status_code == 200
    data = response.json()
    if doc_id:
        assert len(calls) == 1
        assert data["sources"] == [{"doc_id": doc_id, "section": metadata["section"],
                                    "title": metadata["title"], "url": metadata["source_url"]}]
        assert data["answer"] == "출처 전송 확인용 테스트 응답"
        assert data["handoff"] is False
    else:
        assert not calls, "doc_id가 없는데 생성 호출로 진행했습니다"
        assert data["sources"] == []
        assert data["handoff"] is True and data["needs_review"] is True
