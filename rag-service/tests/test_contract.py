"""약속 확인 테스트 — 누가 무엇을 고쳐도 이 테스트는 통과해야 한다.

실행 (rag-service/ 에서):  ../.venv/bin/python -m pytest -q tests
검색·LLM 은 가짜로 바꿔서 돌리므로 OpenAI 호출·비용이 없다.
생성 쪽은 구조화된 LLM(build_document_llm)과 검증 LLM(build_verification_llm)을 쓰므로 둘 다 가짜로 바꾼다.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import rag.chain
from rag import generator
from app import auth
from app.main import app as fastapi_app
from rag.schema import TOPIC_CHEMICAL, TOPIC_LAW

SECRET = "test-secret"
QUOTE = "가상 안내표의 색상은 청록색입니다."
CONDITION = "가상 교육 화면에 한정됩니다."
FAKE_META = {"doc_id": "S1", "doc_type": "guide", "chunk_id": "S1-test", "law_name": "", "article_no": "",
             "title": "가상 안내 자료", "section": "1.1 시험용 절", "source_url": "https://example.invalid/contract-test"}
FAKE_HIT = {"text": QUOTE + "\n" + CONDITION, "score": 0.2, "metadata": FAKE_META}
FAKE_DRAFT = {"supported": True, "statements": [{
    "kind": "information", "text": QUOTE,
    "citations": [{"chunk_id": FAKE_META["chunk_id"], "quote": QUOTE}],
    "conditions": [{"text": CONDITION, "citations": [{"chunk_id": FAKE_META["chunk_id"], "quote": CONDITION}]}],
}]}


class FakeLLM:
    """구조화 출력 LLM 자리 (생성용·검증용 공통). invoke 결과를 정해 둔다."""
    def __init__(self, result):
        self.result = result

    def invoke(self, messages):
        return self.result(messages) if callable(self.result) else self.result


def _all_supported(messages):
    data = json.loads(messages[1].content.split("\n", 1)[1])
    return {"assessments": [{"claim_id": c["claim_id"], "verdict": "supported"} for c in data["claims"]]}
RESPONSE_KEYS = {"answer", "sources", "needs_review", "handoff", "latency_ms"}


def make_token(secret: str = SECRET) -> str:
    now = int(time.time())
    return jwt.encode({"sub": "1", "username": "tester", "iss": auth.ISSUER, "iat": now, "exp": now + 600},
                      secret, algorithm=auth.ALGORITHM)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    return TestClient(fastapi_app)


@pytest.fixture
def logged_in(client):
    client.cookies.set("ACCESS_TOKEN", make_token())
    return client


@pytest.fixture
def fake_search(monkeypatch):
    """검색 결과를 정해 두는 도우미: fake_search([]) 또는 fake_search([FAKE_HIT])."""
    def _set(hits):
        monkeypatch.setattr(rag.chain, "retrieve", lambda *a, **k: hits)
    monkeypatch.setattr(rag.chain.stores, "get_store", lambda topic: object())
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: FakeLLM(FAKE_DRAFT))
    monkeypatch.setattr(generator, "build_verification_llm", lambda *a, **k: FakeLLM(_all_supported))
    return _set


def ask(c, **body):
    body.setdefault("topic", TOPIC_LAW)
    return c.post("/rag-query", json=body)


# --- 인증 ---------------------------------------------------------------
def test_no_token_is_401(client):
    assert ask(client, question="중대재해법의 기준은?").status_code == 401


def test_forged_token_is_401(client):
    client.cookies.set("ACCESS_TOKEN", make_token("wrong-secret"))
    assert ask(client, question="중대재해법의 기준은?").status_code == 401


# --- 요청 형식 ------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {"question": "중대재해법의 기준은?", "topic": "etc"},           # 없는 topic
    {"question": "중대재해법의 기준은?", "language": "ja"},         # 지원하지 않는 언어
    {"question": "a"},                                               # 너무 짧은 질문
])
def test_bad_request_is_422(logged_in, body):
    assert ask(logged_in, **body).status_code == 422


# --- 응답 형식 · 규칙 ---------------------------------------------------------
@pytest.mark.parametrize("language", ["ko", "zh", "vi", "en", "km"])
def test_all_languages_accepted(logged_in, fake_search, language):
    fake_search([FAKE_HIT])
    assert ask(logged_in, question="사망자가 발생하면 처벌은?", language=language).status_code == 200


def test_equipment_id_accepted(logged_in, fake_search):
    fake_search([FAKE_HIT])
    r = ask(logged_in, question="탱크 열 때 주의할 점은?", topic=TOPIC_CHEMICAL, equipment_id="DEMO-WET-01")
    assert r.status_code == 200


def test_answer_has_contract_fields(logged_in, fake_search):
    fake_search([FAKE_HIT])
    r = ask(logged_in, question="가상 안내표 자료를 설명해 주세요", topic=TOPIC_CHEMICAL)
    assert r.status_code == 200
    data = r.json()
    assert RESPONSE_KEYS <= data.keys()
    assert data["sources"] and {"doc_id", "section", "title", "url"} <= data["sources"][0].keys()
    assert data["sources"][0]["section"] == FAKE_META["section"] and QUOTE in data["answer"]


def test_no_hits_means_not_found_and_handoff(logged_in, fake_search, monkeypatch):
    fake_search([])
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: pytest.fail("근거가 없는데 LLM 을 불렀습니다"))
    data = ask(logged_in, question="이 약품 단가는 얼마야?", topic=TOPIC_CHEMICAL).json()
    assert data["handoff"] is True and data["sources"] == []


def test_judgement_question_is_handoff(logged_in, fake_search):
    fake_search([FAKE_HIT])
    data = ask(logged_in, question="우리 회사 사고에 대표이사가 책임이 있나요?").json()
    assert data["handoff"] is True


def test_emergency_question_is_handoff(logged_in, fake_search):
    fake_search([])
    data = ask(logged_in, question="불산이 피부에 닿았어요", topic=TOPIC_CHEMICAL).json()
    assert data["handoff"] is True and "119" in data["answer"]


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code in (200, 503) and {"ready", "indexes"} <= r.json().keys()
