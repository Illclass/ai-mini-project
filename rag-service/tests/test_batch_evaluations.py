"""Batch diagnostics use the real chain and synthetic evidence; no model/network calls."""
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import secrets
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from app import auth, main
from rag import chain, generator, stores
from rag.schema import ENV_JWT_SECRET, RagRequest, RagResponse, TOPIC_LAW
from tests.test_contract import FAKE_DRAFT, FAKE_HIT, FakeLLM, _all_supported


EVALUATION_PATH = "/rag-query/evaluations"
DATASET_ROOT = Path(__file__).resolve().parents[1] / "eval" / "datasets"
ORIGINAL_EVALUATION_PAIRS_SHA256 = "fd692cb5be8dbd088dd23f2a3f80f3ec3aca66dcad0a64050dfd2eeefc617ec2"
VALIDATION_V1_PAIRS_SHA256 = "cdc00cff8366c38d5d357b8bc9b1a16307469fa48de4571acc9de3d4abb5dc52"


def _pair_fingerprint(cases):
    pairs = [{"id": case["id"], "request": case["request"], "expected": case["expected"]} for case in cases]
    content = json.dumps(pairs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _case(case_id, *, question="가상 안내표 자료를 설명해 주세요", expected=None, split="test"):
    return {
        "id": case_id, "split": split, "category": "synthetic",
        "request": RagRequest(question=question, topic=TOPIC_LAW).model_dump(),
        "expected": expected or {"http_status": 200, "outcome": "answered", "handoff": False,
                                  "sources_min": 1, "source_doc_ids_any": ["S1"]},
    }


def _dataset(path, cases):
    path.write_text(json.dumps({"version": 1, "name": "unit-evaluation", "description": "synthetic only",
                                "cases": cases}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def batch_api(monkeypatch, tmp_path):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv(ENV_JWT_SECRET, secret)
    monkeypatch.setattr(main, "_EVALUATION_ROOT", tmp_path)
    monkeypatch.setattr(main, "latency_stats", main.LatencyStatistics())
    monkeypatch.setattr(stores, "get_store", lambda topic: object())
    retrieve = Mock(return_value=[deepcopy(FAKE_HIT)])
    monkeypatch.setattr(chain, "retrieve", retrieve)
    answer = Mock(wraps=chain.answer)
    monkeypatch.setattr(main, "answer", answer)
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: FakeLLM(deepcopy(FAKE_DRAFT)))
    monkeypatch.setattr(generator, "build_verification_llm", lambda *a, **k: FakeLLM(_all_supported))
    token = jwt.encode({"sub": "batch-test-user", "iss": auth.ISSUER, "exp": int(time.time()) + 600},
                       secret, algorithm=auth.ALGORITHM)
    headers = {"Authorization": "Bearer " + token, "Origin": "http://localhost:5174"}
    return TestClient(main.app), headers, tmp_path, answer, retrieve, secret


def test_batch_reports_each_case_and_continues_after_failure_and_error(batch_api):
    client, headers, root, answer, retrieve, _ = batch_api
    invalid = _case("invalid", expected={"http_status": 422, "outcome": "error", "reason_any": ["invalid_request"]})
    invalid["request"]["topic"] = "invalid"
    cases = [
        _case("answered"),
        _case("wrong-expectation", question="이 작업을 승인해줘"),
        _case("upstream", question="TIMEOUT_CASE", split="validation",
              expected={"http_status": 503, "outcome": "error", "reason_any": ["llm_timeout"]}),
        invalid,
    ]
    def search(question, *args, **kwargs):
        if question == "TIMEOUT_CASE":
            raise TimeoutError("PRIVATE_PROVIDER_DETAILS")
        return [deepcopy(FAKE_HIT)]
    retrieve.side_effect = search
    path = _dataset(root / "mixed.json", cases)
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
    data = response.json()
    assert response.status_code == 200 and data["total_cases"] == 4
    assert data["summary"]["passed"] == 3 and data["summary"]["failed"] == 1
    assert data["summary"]["error_count"] == 2  # 503 and request-validation 422
    assert data["summary"]["duration_ms"] >= 0
    assert {row["case_id"]: row["passed"] for row in data["results"]} == {
        "answered": True, "wrong-expectation": False, "upstream": True, "invalid": True,
    }
    assert [row["http_status"] for row in data["results"]] == [200, 200, 503, 422]
    assert data["results"][1]["failure"]["reason"] == "out_of_scope"
    assert data["results"][2]["failure"]["stage"] == "retrieval"
    assert data["results"][3]["failure"]["reason"] == "invalid_request"
    assert answer.call_count == 3 and retrieve.call_count == 2
    assert "PRIVATE_PROVIDER_DETAILS" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    for row in data["results"]:
        assert {"request_id", "http_status", "outcome", "response", "failure", "timing", "trace", "trace_truncated"} <= row.keys()
        assert row["checks"] and all("passed" in check for check in row["checks"])


def test_case_contexts_are_independent_and_internal_error_does_not_stop_batch(batch_api):
    client, headers, root, answer, _, _ = batch_api
    path = _dataset(root / "independent.json", [
        _case("broken", question="BROKEN_CASE", expected={"http_status": 500, "outcome": "error", "reason_any": ["internal_error"]}),
        _case("healthy", split="validation"),
    ])
    def execute(request):
        if request.question == "BROKEN_CASE":
            raise KeyError("PRIVATE_INTERNAL_DETAILS")
        return chain.answer(request)
    answer.side_effect = execute
    data = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers).json()
    broken, healthy = data["results"]
    assert broken["passed"] and healthy["passed"]
    assert healthy["failure"] is None and healthy["outcome"] == "answered"
    assert broken["request_id"] != healthy["request_id"] != data["run_id"]
    assert all(event.get("reason") != "internal_error" for event in healthy["trace"])
    assert main._active_trace.get() is None
    assert answer.call_count == 2


def test_batch_auth_is_shared_and_logs_redact_dataset_contents(batch_api, caplog):
    client, headers, root, answer, _, secret = batch_api
    caplog.set_level(logging.INFO, logger="chembridge.trace")
    path = _dataset(root / "private.json", [_case("one", question="PRIVATE_BATCH_QUESTION"), _case("two")])
    response = client.post(EVALUATION_PATH + "?token=PRIVATE_BATCH_QUERY", json={"dataset_path": str(path)}, headers=headers)
    data = response.json()
    assert response.status_code == 200 and answer.call_count == 2
    ids = {row["request_id"] for row in data["results"]}
    assert len(ids) == 2 and data["run_id"] not in ids
    for row in data["results"]:
        auth_event = next(event for event in row["trace"] if event["stage"] == "authentication")
        assert auth_event["status"] == "skipped" and auth_event["reason"] == "batch_authentication_reused"
        assert row["timing"]["scope"] == "response_ready"
        assert [event["sequence"] for event in row["trace"]] == list(range(1, len(row["trace"]) + 1))
    for private in ("PRIVATE_BATCH_QUESTION", "PRIVATE_BATCH_QUERY", "batch-test-user", secret, headers["Authorization"]):
        assert private not in caplog.text
        assert all(private not in json.dumps(row["trace"], ensure_ascii=False) for row in data["results"])
    assert main._active_trace.get() is None
    # A second batch gets fresh case IDs and counters rather than previous traces.
    second = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers).json()
    assert ids.isdisjoint({row["request_id"] for row in second["results"]})


@pytest.mark.parametrize("kind, expected", [
    ("missing", 404), ("invalid_json", 422), ("wrong_schema", 422),
    ("empty", 422), ("duplicate_id", 422), ("wrong_extension", 422),
])
def test_bad_dataset_is_rejected_before_chain_execution(batch_api, kind, expected):
    client, headers, root, answer, _, _ = batch_api
    path = root / "bad.json"
    if kind == "invalid_json":
        path.write_text("{PRIVATE_FILE_CONTENT", encoding="utf-8")
    elif kind == "wrong_schema":
        path.write_text(json.dumps({"cases": [{"id": "x"}]}), encoding="utf-8")
    elif kind == "empty":
        _dataset(path, [])
    elif kind == "duplicate_id":
        _dataset(path, [_case("same"), _case("same")])
    elif kind == "wrong_extension":
        path = _dataset(root / "cases.txt", [_case("one")])
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
    assert response.status_code == expected
    assert "PRIVATE_FILE_CONTENT" not in response.text
    answer.assert_not_called()


def test_path_cannot_escape_evaluation_directory_or_follow_external_symlink(batch_api):
    client, headers, root, answer, _, _ = batch_api
    outside = _dataset(root.parent / (root.name + "-outside.json"), [_case("outside")])
    symlink = root / "linked.json"
    symlink.symlink_to(outside)
    for path in (outside, symlink):
        response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
        assert response.status_code == 422
    answer.assert_not_called()


def test_unreadable_dataset_is_503(batch_api, monkeypatch):
    client, headers, root, answer, _, _ = batch_api
    path = _dataset(root / "unreadable.json", [_case("one")])
    original = Path.open
    def unreadable(self, *args, **kwargs):
        if self == path:
            raise PermissionError("PRIVATE_FILE_DETAILS")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", unreadable)
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
    assert response.status_code == 503 and "PRIVATE_FILE_DETAILS" not in response.text
    answer.assert_not_called()


def test_batch_requires_auth_and_openapi_documents_path_body(batch_api):
    client, _, root, answer, _, _ = batch_api
    path = _dataset(root / "auth.json", [_case("one")])
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)})
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
    answer.assert_not_called()
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][EVALUATION_PATH]["post"]
    assert {"BearerAuth": []} in operation["security"]
    assert "requestBody" in operation
    body_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    body_schema = schema["components"]["schemas"][body_ref.rsplit("/", 1)[-1]]
    assert set(body_schema["properties"]) == {"dataset_path"}
    assert body_schema["required"] == ["dataset_path"]


@pytest.mark.parametrize("name, split", [("evaluation", "test"), ("validation", "validation")])
def test_shipped_datasets_have_40_unique_pairs_and_one_purpose(name, split):
    path = DATASET_ROOT / (name + ".json")
    dataset = json.loads(path.read_text(encoding="utf-8"))
    main._EvaluationDataset.model_validate(dataset)
    cases = dataset["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 40
    assert {case["split"] for case in cases} == {split}
    for case in cases:
        if case["expected"]["http_status"] == 422:
            with pytest.raises(ValidationError):
                RagRequest.model_validate(case["request"])
        else:
            RagRequest.model_validate(case["request"])
        assert {"http_status", "outcome"} <= case["expected"].keys()
        assert case["expected"]["outcome"] in {"answered", "held", "error"}


def test_evaluation_preserves_the_original_40_question_expectation_pairs():
    dataset = json.loads((DATASET_ROOT / "evaluation.json").read_text(encoding="utf-8"))
    # Moving and relabelling the development set must not silently change its
    # existing questions or expected outcomes while creating the held-out set.
    assert _pair_fingerprint(dataset["cases"]) == ORIGINAL_EVALUATION_PAIRS_SHA256


def test_validation_v1_question_expectation_pairs_are_frozen():
    dataset = json.loads((DATASET_ROOT / "validation.json").read_text(encoding="utf-8"))
    # A final validation set must not be retuned to match observed model errors.
    # Deliberate dataset revisions require explicit review and a new fingerprint.
    assert dataset["version"] == 1
    assert _pair_fingerprint(dataset["cases"]) == VALIDATION_V1_PAIRS_SHA256


def test_evaluation_and_validation_have_no_shared_question_strings():
    def ids(name):
        dataset = json.loads((DATASET_ROOT / (name + ".json")).read_text(encoding="utf-8"))
        return {case["id"] for case in dataset["cases"]}

    def questions(name):
        dataset = json.loads((DATASET_ROOT / (name + ".json")).read_text(encoding="utf-8"))
        return {" ".join(case["request"]["question"].split()).casefold() for case in dataset["cases"]
                if isinstance(case["request"].get("question"), str)}
    # Translated intent families are reviewed separately; this catches direct
    # copies and formatting-only duplicates across the two managed datasets.
    assert questions("evaluation").isdisjoint(questions("validation"))
    assert ids("evaluation").isdisjoint(ids("validation"))


@pytest.mark.parametrize("name, split", [("evaluation", "test"), ("validation", "validation")])
def test_entire_shipped_dataset_executes_with_isolated_diagnostics(batch_api, monkeypatch, name, split):
    client, headers, root, _, _, _ = batch_api
    shipped = DATASET_ROOT / (name + ".json")
    dataset = json.loads(shipped.read_text(encoding="utf-8"))
    # Product resolution/translation is irrelevant to batch orchestration and
    # must not cause live calls in this execution test.
    monkeypatch.setattr(chain, "resolve_product_id", lambda question, topic, language, product_id, equipment_id: product_id)
    target = root / "datasets" / (name + ".json")
    target.parent.mkdir()
    _dataset(target, dataset["cases"])
    response = client.post(EVALUATION_PATH, json={"dataset_path": "eval/datasets/" + name + ".json"}, headers=headers)
    data = response.json()
    assert response.status_code == 200 and data["total_cases"] == len(data["results"]) == 40
    assert data["run_id"] == response.headers["x-request-id"]
    assert len({row["request_id"] for row in data["results"]}) == 40
    assert data["summary"]["passed"] + data["summary"]["failed"] == 40
    assert data["summary"]["by_split"][split]["total"] == 40
    assert data["summary"]["by_split"]["validation" if split == "test" else "test"]["total"] == 0
    assert all(row["trace"] and row["checks"] for row in data["results"])


def test_original_dataset_path_aliases_the_development_evaluation_file(batch_api):
    client, headers, root, answer, _, _ = batch_api
    target = root / "datasets" / "evaluation.json"
    target.parent.mkdir()
    _dataset(target, [_case("legacy-path")])
    response = client.post(EVALUATION_PATH, json={"dataset_path": "eval/diagnostic_cases_40.json"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["dataset_path"] == "eval/datasets/evaluation.json"
    assert response.json()["results"][0]["case_id"] == "legacy-path"
    assert answer.call_count == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "\ud800"])
def test_non_json_values_rejected_before_any_execution(batch_api, value):
    client, headers, root, answer, _, _ = batch_api
    case = _case("invalid-encoding")
    case["request"]["question"] = value
    # Escaped surrogate / NaN can be decoded by Python despite not being safe
    # response JSON. Reject the whole dataset before spending model calls.
    path = root / "invalid-encoding.json"
    path.write_text(json.dumps({"version": 1, "name": "invalid", "cases": [case]}), encoding="utf-8")
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
    assert response.status_code == 422
    answer.assert_not_called()


def test_invalid_path_is_422_and_unserializable_case_does_not_lose_batch(batch_api):
    client, headers, root, answer, _, _ = batch_api
    assert client.post(EVALUATION_PATH, json={"dataset_path": "bad.json\u0000"}, headers=headers).status_code == 422
    answer.assert_not_called()
    def execute(request):
        return RagResponse(answer="\ud800") if request.question == "BAD_OUTPUT" else chain.answer(request)
    answer.side_effect = execute
    path = _dataset(root / "output.json", [
        _case("bad-output", question="BAD_OUTPUT", expected={"http_status": 500, "outcome": "error", "reason_any": ["internal_error"]}),
        _case("next"),
    ])
    response = client.post(EVALUATION_PATH, json={"dataset_path": str(path)}, headers=headers)
    data = response.json()
    assert response.status_code == 200
    assert [row["http_status"] for row in data["results"]] == [500, 200]
    assert all(row["passed"] for row in data["results"])
