"""검색 규칙 테스트 — 담당: 김규빈. 인덱스·LLM 없이 돈다.

- 물질명 → 제품 자동 지정 (rag/products.py)
- 경고 문맥이 잘린 MSDS 청크 제외 (rag/retriever.drop_truncated)
"""
import pytest

from rag import products, retriever
from rag.schema import TOPIC_CHEMICAL, TOPIC_LAW

TABLE = {"불산": {"sigma-695068"}, "황산": {"sigma-339741"}, "과산화수소": {"merck-8.22287"},
         "TMAH": {"sigma-328251"}, "IPA": {"sigma-563935"}}


@pytest.fixture(autouse=True)
def fake_index(monkeypatch):
    monkeypatch.setattr(products, "products_by_substance", lambda: TABLE)
    monkeypatch.setattr(products, "to_korean", lambda q, lang: q)   # 번역 LLM 을 부르지 않는다


@pytest.mark.parametrize("question, expected", [
    ("불산 취급 시 필요한 보호구는?", "sigma-695068"),
    ("불화수소 보관 방법", "sigma-695068"),
    ("What PPE do I need for hydrofluoric acid?", "sigma-695068"),
    ("硫酸转移时要注意什么？", "sigma-339741"),
    ("현상액이 손에 묻었어요", "sigma-328251"),
    ("ipa 보관은?", "sigma-563935"),
])
def test_one_substance_picks_its_product(question, expected):
    assert products.resolve_product_id(question, TOPIC_CHEMICAL) == expected


@pytest.mark.parametrize("question", [
    "보호구는 무엇을 착용해야 하나요?",          # 물질명 없음
    "황산과 과산화수소를 섞으면 위험한가요?",      # 물질 두 개
    "HFC 냉매 누출 시 대응은?",                    # HF 가 HFC 에 걸리면 안 됨
])
def test_no_or_many_substances_picks_nothing(question):
    assert products.resolve_product_id(question, TOPIC_CHEMICAL) is None


def test_request_product_id_wins_and_law_topic_is_untouched():
    assert products.resolve_product_id("불산 보호구", TOPIC_CHEMICAL, product_id="sigma-339741") == "sigma-339741"
    assert products.resolve_product_id("불산 사고 처벌", TOPIC_LAW) is None


def test_equipment_limits_candidates():
    # Wet Bench 에는 황산·과산화수소가 있고 IPA 는 없다 → IPA 질문은 자동 지정하지 않는다
    assert products.resolve_product_id("황산 교체 전 확인", TOPIC_CHEMICAL, equipment_id="DEMO-WET-01") == "sigma-339741"
    assert products.resolve_product_id("IPA 보관", TOPIC_CHEMICAL, equipment_id="DEMO-WET-01") is None


def _hit(cid, doc_type="msds"):
    return {"text": cid, "score": 0.1, "metadata": {"chunk_id": cid, "doc_type": doc_type}}


def test_drop_truncated_removes_only_flagged_msds(monkeypatch):
    import rag.prompt
    monkeypatch.setattr(rag.prompt, "incomplete_critical_chunks",
                        lambda docs: {d.metadata["chunk_id"] for d in docs if d.metadata["chunk_id"].endswith("-bad")})
    hits = [_hit("D2-s8"), _hit("D2-s7-bad"), _hit("K8-9_1-bad", "guide")]
    assert [h["metadata"]["chunk_id"] for h in retriever.drop_truncated(hits)] == ["D2-s8", "K8-9_1-bad"]


def test_drop_truncated_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(retriever, "DROP_TRUNCATED", False)
    hits = [_hit("D2-s7-bad")]
    assert retriever.drop_truncated(hits) == hits


class _FakeDoc:
    def __init__(self, cid, no, text, pid="sigma-695068"):
        self.page_content = text
        self.metadata = {"chunk_id": cid, "doc_type": "msds", "product_id": pid, "msds_section_no": no}


class _FakeStore:
    def __init__(self, docs):
        self.docstore = type("DS", (), {"_dict": {d.metadata["chunk_id"]: d for d in docs}})()


def test_attach_identity_adds_sections_1_3_16_once():
    store = _FakeStore([
        _FakeDoc("D2-s1", 1, "제품명 : HF\n제품 번호 : 695068"), _FakeDoc("D2-s3", 3, "함유량 (% w/w) >= 45"),
        _FakeDoc("D2-s16", 16, "약어 설명"), _FakeDoc("D2-s16-2", 16, "최종 개정일자 : 2026.07.17"),
        _FakeDoc("D2-s8", 8, "보호구"), _FakeDoc("D1-s1", 1, "제품 번호 : 339741", pid="sigma-339741"),
    ])
    hits = [_hit("D2-s8"), _hit("D2-s1")]   # 1항은 이미 검색됨 → 다시 붙이지 않는다
    out = [h["metadata"]["chunk_id"] for h in retriever.attach_identity(hits, store, "sigma-695068")]
    assert out == ["D2-s8", "D2-s1", "D2-s3", "D2-s16-2"]


def test_attach_identity_needs_one_product():
    assert retriever.attach_identity([_hit("D2-s8")], _FakeStore([]), None) == [_hit("D2-s8")]
