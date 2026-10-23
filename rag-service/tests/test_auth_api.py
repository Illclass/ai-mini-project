"""인증 연동·CORS·로그 회귀 테스트. 외부 서비스 호출 없이 검증한다."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import secrets
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import auth, main
from rag.schema import DOC_TYPE_LAW, ENV_JWT_SECRET, LANGUAGES, TOPIC_LAW, TOPICS, RagRequest, RagResponse, make_chunk_id


@pytest.fixture(autouse=True)
def isolated_latency(monkeypatch):
    stats = main.LatencyStatistics()
    monkeypatch.setattr(main, "latency_stats", stats)
    return stats


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
                     if record.name in ("chembridge.requests", "chembridge.latency", "app.main", "root"))


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


def test_latency_separates_statuses_and_routes(api, monkeypatch, isolated_latency):
    client, secret = api
    headers = {"Authorization": "Bearer " + token(secret)}
    monkeypatch.setattr(main.stores, "is_ready", lambda: True)
    monkeypatch.setattr(main.stores, "status", lambda: {topic: True for topic in TOPICS})
    # 보류 응답은 HTTP 실패가 아니며, 인증/형식/의존성 오류와 분리한다.
    monkeypatch.setattr(main, "answer", lambda req: RagResponse(answer="판단 보류", handoff=True, needs_review=True))
    assert client.post("/rag-query", json=body(), headers=headers).status_code == 200
    assert client.post("/rag-query", json=body()).status_code == 401
    assert client.post("/rag-query", json={**body(), "topic": "invalid"}, headers=headers).status_code == 422

    def fail(req):
        raise TimeoutError("PRIVATE_FAILURE_MARKER")
    monkeypatch.setattr(main, "answer", fail)
    assert client.post("/rag-query", json=body(), headers=headers).status_code == 503
    main.app.dependency_overrides[auth.get_current_user] = lambda: 1 / 0
    assert client.post("/rag-query", json=body()).status_code == 500
    assert client.get("/health").status_code == 200

    snapshot = isolated_latency.snapshot()
    total = snapshot["overall"]
    assert total["request_count"] == total["completed_count"] == 6
    assert total["incomplete_count"] == 0
    assert total["client_error_count"] == total["server_error_count"] == 2
    assert total["failure_count"] == 4
    rag = next(row for row in snapshot["routes"] if row["path"] == "/rag-query")
    assert rag["method"] == "POST" and rag["request_count"] == 5
    assert rag["status_counts"] == {"200": 1, "401": 1, "422": 1, "500": 1, "503": 1}
    assert rag["by_status"]["200"]["failure_count"] == 0
    assert all(row["request_count"] == 1 for row in rag["by_status"].values())


def test_latency_snapshot_concurrent_updates_and_atomic_file(tmp_path):
    stats = main.LatencyStatistics()
    target = tmp_path / "latency.json"
    stats.enable_file(target)

    def record(index):
        stats.record("/rag-query", "POST", 200 if index % 2 == 0 else 503, index + 1, True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(record, range(100)))

    snapshot = stats.snapshot()
    overall = snapshot["overall"]
    assert overall["request_count"] == overall["completed_count"] == 100
    assert overall["latency_ms"] == {"sum": 5050, "min": 1, "avg": 50.5, "max": 100}
    assert overall["error_rate"] == .5 and overall["failure_count"] == 50
    assert overall["status_counts"] == {"200": 50, "503": 50}
    by_status = snapshot["routes"][0]["by_status"]
    assert by_status["200"]["latency_ms"]["avg"] == 50
    assert by_status["503"]["latency_ms"]["avg"] == 51
    saved = json.loads(target.read_text())
    assert saved["overall"] == overall and saved["routes"] == snapshot["routes"]
    assert saved["scope"] == "http_process_lifetime"
    assert not target.with_suffix(".tmp").exists()
    assert main.LatencyStatistics().snapshot()["overall"]["request_count"] == 0


@pytest.mark.parametrize("case", ["missing", "expired", "forged", "invalid_bearer_with_cookie"])
def test_log_endpoint_requires_valid_auth(api, case):
    client, secret = api
    headers = {}
    if case == "expired":
        headers["Authorization"] = "Bearer " + token(secret, exp=0)
    elif case == "forged":
        headers["Authorization"] = "Bearer " + token(secrets.token_urlsafe(32))
    elif case == "invalid_bearer_with_cookie":
        client.cookies.set("ACCESS_TOKEN", token(secret))
        headers["Authorization"] = "Bearer invalid"
    response = client.get("/raq-query-log", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "logs" not in response.json()


def test_log_endpoint_exposes_safe_live_events_and_summary(api, isolated_latency, monkeypatch):
    client, secret = api
    encoded = token(secret)
    headers = {"Authorization": "Bearer " + encoded, "Origin": "http://localhost:5174"}
    payload = body()
    calls = []

    def answer(req):
        calls.append(req)
        return RagResponse(answer="PRIVATE_ANSWER_MARKER")
    monkeypatch.setattr(main, "answer", answer)
    assert client.post("/rag-query?key=PRIVATE_QUERY_MARKER", json=payload, headers=headers).status_code == 200
    assert client.post("/rag-query", json=payload).status_code == 401
    response = client.get("/raq-query-log", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    data = response.json()
    assert data["overall"]["request_count"] == 2
    assert data["overall"]["failure_count"] == 1
    assert [event["status"] for event in data["logs"]] == [401, 200]
    assert [event["sequence"] for event in data["logs"]] == [2, 1]
    assert data["logs"][0]["level"] == "WARNING"
    assert data["logs"][0]["outcome"] == "client_error"
    assert data["logs"][1]["outcome"] == "completed"
    assert all(event["completed"] and event["latency_ms"] >= 0 and event["recorded_at"] for event in data["logs"])
    for private in (payload["question"], "PRIVATE_ANSWER_MARKER", "PRIVATE_QUERY_MARKER", encoded, secret, "tester"):
        assert private not in response.text
    # 반복 조회 자체는 집계·최근 요청 목록을 바꾸거나 RAG를 호출하지 않는다.
    assert client.get("/raq-query-log", headers=headers).json()["logs"] == data["logs"]
    assert isolated_latency.snapshot()["overall"]["request_count"] == 2
    assert len(calls) == 1


def test_log_endpoint_cookie_auth_and_empty_state(api):
    client, secret = api
    client.cookies.set("ACCESS_TOKEN", token(secret))
    response = client.get("/raq-query-log")
    assert response.status_code == 200
    data = response.json()
    assert data["logs"] == [] and data["routes"] == []
    assert data["overall"]["request_count"] == 0
    assert data["retention"] == {"max_entries": 1000, "retained_count": 0, "matching_count": 0}


def test_log_endpoint_filters_only_events_and_caps_retention(api, isolated_latency):
    client, secret = api
    # 운영 파일을 읽지 않으며 오래된 요청부터 1000건 버퍼에서 제거한다.
    for index in range(1002):
        isolated_latency.record("/rag-query", "POST", 200 if index % 2 == 0 else 503, index, True)
    isolated_latency.record("/health", "GET", 200, 1, True)
    headers = {"Authorization": "Bearer " + token(secret)}
    response = client.get("/raq-query-log", params={"limit": 2, "path": "/rag-query", "status": 503}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["logs"]) == 2
    assert [event["sequence"] for event in data["logs"]] == [1002, 1000]
    assert data["filters"] == {"path": "/rag-query", "status": 503, "limit": 2}
    assert data["retention"] == {"max_entries": 1000, "retained_count": 1000, "matching_count": 500}
    assert data["overall"]["request_count"] == 1003
    assert len(data["routes"]) == 2
    all_events = client.get("/raq-query-log?limit=1000", headers=headers).json()["logs"]
    assert len(all_events) == 1000 and all_events[-1]["sequence"] == 4
    assert client.get("/raq-query-log?status=404", headers=headers).json()["logs"] == []
    # 조회 결과를 수정해도 내부 메모리를 변경하지 않는다.
    snapshot = isolated_latency.query_logs(1, None, None)
    snapshot["logs"][0]["path"] = "PRIVATE_MUTATION"
    assert isolated_latency.query_logs(1, None, None)["logs"][0]["path"] == "/health"


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "limit=abc", "status=99", "status=600", "path=/PRIVATE_PATH"])
def test_log_endpoint_rejects_invalid_filters(api, query):
    client, secret = api
    response = client.get("/raq-query-log?" + query, headers={"Authorization": "Bearer " + token(secret)})
    assert response.status_code == 422


def test_log_endpoint_missing_auth_configuration_is_503(api, monkeypatch):
    client, secret = api
    monkeypatch.delenv(ENV_JWT_SECRET)
    response = client.get("/raq-query-log", headers={"Authorization": "Bearer " + token(secret)})
    assert response.status_code == 503 and "logs" not in response.json()


def test_latency_file_failure_keeps_response_and_memory_stats(api, tmp_path, caplog, isolated_latency):
    client, secret = api
    blocked = tmp_path / "PRIVATE_PATH_MARKER"
    blocked.write_text("not a directory")
    isolated_latency.enable_file(blocked / "latency.json")
    for _ in range(2):
        assert client.post("/rag-query", json=body(), headers={"Authorization": "Bearer " + token(secret)}).status_code == 200
    assert isolated_latency.snapshot()["overall"]["request_count"] == 2
    warnings = [r.getMessage() for r in caplog.records if r.name == "chembridge.latency"]
    assert warnings == ["지연 통계 파일 기록 실패: 메모리 집계는 유지합니다."]
    assert "PRIVATE_PATH_MARKER" not in caplog.text


def test_latency_snapshot_hides_input_and_tracks_preflight(api, tmp_path, caplog, isolated_latency):
    client, secret = api
    caplog.set_level(logging.INFO)
    target = tmp_path / "latency.json"
    isolated_latency.enable_file(target)
    encoded = token(secret)
    client.post("/rag-query?token=PRIVATE_QUERY_MARKER", json=body(),
                headers={"Authorization": "Bearer " + encoded, "Cookie": "PRIVATE_COOKIE_MARKER"})
    client.request("PRIVATE_METHOD_MARKER", "/PRIVATE_PATH_MARKER")
    client.options("/rag-query", headers={"Origin": "http://localhost:5174",
                                           "Access-Control-Request-Method": "POST"})
    saved = target.read_text()
    for private in ("PRIVATE_QUERY_MARKER", "PRIVATE_QUESTION_MARKER", "PRIVATE_COOKIE_MARKER",
                    "PRIVATE_METHOD_MARKER", "PRIVATE_PATH_MARKER", encoded, secret):
        assert private not in saved and private not in app_logs(caplog)
    routes = {(row["path"], row["method"]): row for row in json.loads(saved)["routes"]}
    assert routes[("/unmatched", "OTHER")]["status_counts"] == {"404": 1}
    assert routes[("/rag-query", "OPTIONS")]["status_counts"] == {"200": 1}


@pytest.mark.parametrize("fail_after_first_body", [False, True])
def test_latency_measures_until_last_body_and_marks_interrupted_send(monkeypatch, isolated_latency, fail_after_first_body):
    clock = [10.0]
    monkeypatch.setattr(main, "perf_counter", lambda: clock[0])

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        if fail_after_first_body:
            raise RuntimeError("PRIVATE_PARTIAL_ERROR")
        await send({"type": "http.response.body", "body": b"end"})
        # 응답 완료 뒤 실행되는 background 작업은 HTTP 응답 지연에서 제외한다.
        clock[0] += 5

    async def send(message):
        # 완결 body를 보내는 시간까지 포함해야 한다.
        clock[0] += .1

    async def receive():
        return {"type": "http.request", "body": b""}

    middleware = main.RequestLogMiddleware(application)
    request = middleware({"type": "http", "path": "/rag-query", "method": "POST"}, receive, send)
    if fail_after_first_body:
        with pytest.raises(RuntimeError, match="응답 전송을 완료하지 못했습니다") as error:
            asyncio.run(request)
        assert "PRIVATE_PARTIAL_ERROR" not in str(error.value)
    else:
        asyncio.run(request)
    total = isolated_latency.snapshot()["overall"]
    assert total["latency_ms"]["avg"] == (200 if fail_after_first_body else 300)
    assert total["incomplete_count"] == total["failure_count"] == int(fail_after_first_body)
    assert total["status_counts"] == {"200": 1}


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
