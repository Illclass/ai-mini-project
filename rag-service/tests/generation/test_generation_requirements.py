"""Offline Generation regressions with synthetic sources and mocked semantics.

The Generation conftest supplies an always-supported semantic verifier. These
cases exercise local source/identifier/requirement guards, not LLM quality.
No API keys, network calls, retrieval, or production safety material are used.
"""
from copy import deepcopy
from datetime import date

import pytest
from langchain_core.documents import Document

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds


NAME = "교육액-A"
TOKEN = "CB_PRODUCT_NAME_1"
AS_OF = date(2026, 10, 23)


def replace_name(value):
    if isinstance(value, str):
        return value.replace("TrainingLiquid-A", NAME)
    if isinstance(value, list):
        return [replace_name(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_name(item) for key, item in value.items()}
    return value


def token_case():
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace("TrainingLiquid-A", NAME).replace(
        "경고: 이 자료를 실제 현장 작업에 사용하지 마세요.",
        f"경고: {NAME}를 실제 현장 작업에 사용하지 마세요.",
    )
    draft = replace_name(synthetic_draft(doc, "zh"))
    cid = doc.metadata["chunk_id"]
    draft["statements"][0]["text"] = f"资料中的产品名称为{TOKEN}。"
    condition = draft["statements"][0]["conditions"][0]
    condition["text"] = f"{TOKEN}仅限2个虚拟培训室。"
    condition["citations"].append({"chunk_id": cid, "quote": f"제품명: {NAME}"})
    passages = prompt.critical_passages([doc])
    for translation in draft["critical_translations"]:
        if NAME in passages[translation["passage_id"]][1]:
            translation["text"] = f"警告：不要将{TOKEN}用于真实现场作业。"
    return doc, draft


def run(documents, draft, *, language="ko", product_id=None):
    originals = deepcopy([doc.model_dump() for doc in documents])
    original_draft = deepcopy(draft)
    result = generator.generate_answer(
        "가상 학습 자료에 적힌 내용을 설명해 주세요.", documents,
        structured_llm=StubLLM(draft), language=language,
        product_id=product_id, as_of=AS_OF,
    )
    assert [doc.model_dump() for doc in documents] == originals
    assert draft == original_draft
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    return result


def rejected(result, reason):
    assert result.sources == []
    assert result.needs_review is True
    assert result.handoff is True
    assert result.review_reasons == [reason]


def test_product_tokens_derive_only_from_labelled_msds_source_names():
    doc, _ = token_case()
    duplicate = Document(page_content=doc.page_content, metadata=deepcopy(doc.metadata))
    duplicate.metadata["chunk_id"] = "same-product-second-chunk"
    guide = Document(page_content="제품명: 미확인제품-B", metadata={"doc_type": "guide", "chunk_id": "guide-name"})
    doc.metadata["product_name"] = "메타데이터만있는이름-C"
    assert prompt.product_name_tokens([doc, duplicate, guide]) == {TOKEN: NAME}


def test_chinese_tokens_restore_literal_name_in_statement_condition_and_warning():
    doc, draft = token_case()
    result = run([doc], draft, language="zh", product_id=PRODUCT_ID)
    assert result.sources
    assert f"资料中的产品名称为{NAME}。" in result.answer
    assert f"{NAME}仅限2个虚拟培训室。" in result.answer
    assert f"警告：不要将{NAME}用于真实现场作业。" in result.answer
    assert "CB_PRODUCT_NAME_" not in result.answer
    assert "教育액-A" not in result.answer
    assert result.needs_review is True and result.handoff is False
    assert result.sources[0].chunk_id == doc.metadata["chunk_id"]
    assert result.sources[0].source_url == doc.metadata["source_url"]


@pytest.mark.parametrize("place", ["statement", "condition", "warning"])
def test_unknown_product_tokens_are_never_displayed(place):
    doc, draft = token_case()
    if place == "statement":
        draft["statements"][0]["text"] = draft["statements"][0]["text"].replace(TOKEN, "CB_PRODUCT_NAME_999")
    elif place == "condition":
        condition = draft["statements"][0]["conditions"][0]
        condition["text"] = condition["text"].replace(TOKEN, "CB_PRODUCT_NAME_999")
    else:
        item = next(item for item in draft["critical_translations"] if TOKEN in item["text"])
        item["text"] = item["text"].replace(TOKEN, "CB_PRODUCT_NAME_999")
    rejected(run([doc], draft, language="zh", product_id=PRODUCT_ID), "invalid_translation")


def test_product_tokens_cannot_make_forged_product_facts_valid():
    doc, draft = token_case()
    fact = next(fact for fact in draft["product_facts"] if fact["field"] == "product_name")
    fact["value"] = "조작제품-B"
    rejected(run([doc], draft, language="zh", product_id=PRODUCT_ID), "product_unverified")


def test_known_name_token_cannot_bind_identity_to_unrelated_guide():
    doc, draft = token_case()
    other = Document(page_content="이것은 별도의 가상 교육 자료입니다.", metadata=deepcopy(doc.metadata))
    other.metadata["chunk_id"] = "unrelated-guide-chunk"
    other.metadata["doc_type"] = "guide"
    draft["statements"][0]["citations"] = [{"chunk_id": other.metadata["chunk_id"], "quote": other.page_content}]
    rejected(run([doc, other], draft, language="zh", product_id=PRODUCT_ID), "invalid_translation")


def test_product_name_citation_and_fact_values_must_remain_original_not_tokens():
    doc, draft = token_case()
    fact = next(fact for fact in draft["product_facts"] if fact["field"] == "product_name")
    fact["value"] = TOKEN
    fact["citations"][0]["quote"] = f"제품명: {TOKEN}"
    rejected(run([doc], draft, language="zh", product_id=PRODUCT_ID), "product_unverified")


def test_original_product_name_remains_accepted_without_tokens():
    doc, draft = token_case()
    draft = _replace_token(draft, NAME)
    result = run([doc], draft, language="zh", product_id=PRODUCT_ID)
    assert result.sources and NAME in result.answer
    assert result.needs_review is True and result.handoff is False


def _replace_token(value, replacement):
    if isinstance(value, str):
        return value.replace(TOKEN, replacement)
    if isinstance(value, list):
        return [_replace_token(item, replacement) for item in value]
    if isinstance(value, dict):
        return {key: _replace_token(item, replacement) for key, item in value.items()}
    return value


def technical_case(doc_type, quote, text, *, kind="information"):
    if doc_type == "msds":
        doc = synthetic_msds()
        draft = synthetic_draft(doc)
        doc.page_content += "\n" + quote
    else:
        doc = Document(page_content=quote, metadata={
            "doc_id": "TECH-GUIDE", "doc_type": doc_type,
            "law_name": "", "article_no": "", "chunk_id": "TECH-GUIDE:1",
            "title": "가상 기술지침", "section": "가상 보관 요구",
            "source_url": "https://example.invalid/fictional-technical-guide",
        })
        draft = {"supported": True, "statements": [], "product_facts": [], "critical_translations": []}
    draft["statements"] = [{"kind": kind, "text": text,
        "citations": [{"chunk_id": doc.metadata["chunk_id"], "quote": quote}], "conditions": []}]
    return doc, draft


@pytest.mark.parametrize("doc_type,quote,text", [
    ("msds", "보호복을 착용하시오.", "자료에서는 보호복을 착용해야 합니다."),
    ("msds", "저장 장소는 열원과 떨어진 곳이어야 합니다.", "자료의 저장 장소는 열원과 떨어진 곳이어야 합니다."),
    ("guide", "저장 장소는 열원과 떨어진 곳이어야 합니다.", "이 가상 지침에서는 저장 장소가 열원과 떨어진 곳이어야 합니다."),
    ("web", "저장 장소는 열원과 떨어진 곳이어야 합니다.", "제공된 자료에서는 저장 장소가 열원과 떨어진 곳이어야 합니다."),
])
def test_technical_source_requirements_keep_strength_without_becoming_legal_duty(doc_type, quote, text):
    doc, draft = technical_case(doc_type, quote, text)
    result = run([doc], draft, product_id=PRODUCT_ID if doc_type == "msds" else None)
    assert result.sources and text in result.answer
    assert "법령 자료의 의무 문구" not in result.answer
    assert result.needs_review is True and result.handoff is False


@pytest.mark.parametrize("doc_type", ["msds", "guide", "web"])
@pytest.mark.parametrize("kind,text", [
    ("legal_obligation", "보호복을 착용해야 합니다."),
    ("information", "법령상 보호복을 착용해야 합니다."),
])
def test_technical_source_cannot_be_promoted_to_legal_duty(doc_type, kind, text):
    doc, draft = technical_case(doc_type, "보호복을 착용하시오.", text, kind=kind)
    result = run([doc], draft, product_id=PRODUCT_ID if doc_type == "msds" else None)
    if kind == "legal_obligation" and doc_type in {"msds", "guide"}:
        assert result.sources and not result.handoff
        assert prompt.TEXT['ko']['legal_obligation'] not in result.answer
        assert prompt.TEXT['ko']['information'] in result.answer
    else:
        rejected(result, "invalid_evidence")


@pytest.mark.parametrize("doc_type", ["msds", "guide", "web"])
def test_recommendation_must_not_be_strengthened_to_requirement(doc_type):
    doc, draft = technical_case(doc_type, "보호복 착용을 권장합니다.", "보호복을 반드시 착용해야 합니다.")
    rejected(run([doc], draft, product_id=PRODUCT_ID if doc_type == "msds" else None), "invalid_evidence")


def test_no_evidence_still_requires_handoff():
    result = run([], {"supported": False, "statements": []})
    rejected(result, "no_evidence")


@pytest.mark.parametrize("doc_type", ["msds", "guide"])
def test_technical_requirement_must_not_be_mislabelled_as_recommendation(doc_type):
    doc, draft = technical_case(doc_type, "보호복을 착용하시오.", "보호복을 착용해야 합니다.", kind="recommendation")
    result = run([doc], draft, product_id=PRODUCT_ID if doc_type == "msds" else None)
    assert result.sources and not result.handoff
    assert "자료에 근거한 일반 정보" in result.answer
    assert "권고 지침" not in result.answer
    assert "보호복을 착용해야 합니다." in result.answer


@pytest.mark.parametrize("quote,accepted", [("신체 보호 : 내-산성이 있는 보호복.", True), ("신체 보호 : 내-산성이 있는 보호복을 권장합니다.", False)])
def test_msds_field_style_ppe_keeps_requirement_vs_recommendation(quote, accepted):
    doc, draft = technical_case("msds", quote, "자료에는 내-산성이 있는 보호복을 착용해야 합니다.")
    result = run([doc], draft, product_id=PRODUCT_ID)
    if accepted:
        assert result.sources and not result.handoff
    else:
        rejected(result, "invalid_evidence")


def test_team_generate_returns_displayable_caution_answer_without_changing_api_keys():
    doc, draft = token_case()
    hit = {"text": doc.page_content, "score": 0.0, "metadata": deepcopy(doc.metadata)}
    result = generator.generate("가상 자료 설명", [hit], "zh", product_id=PRODUCT_ID, structured_llm=StubLLM(draft))
    assert result.needs_review and not result.handoff
    assert NAME in result.answer and TOKEN not in result.answer
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff", "latency_ms"}
    assert result.sources[0].doc_id == doc.metadata["doc_id"]


@pytest.mark.parametrize("bad", ["xCB_PRODUCT_NAME_999", "CB_PRODUCT_NAME_", "CB_PRODUCT_NAME_1_BAD"])
def test_malformed_or_ascii_prefixed_tokens_are_not_released(bad):
    doc, draft = token_case()
    draft["statements"][0]["text"] = "产品名称是 " + bad + "。"
    rejected(run([doc], draft, language="zh", product_id=PRODUCT_ID), "invalid_translation")


@pytest.mark.parametrize("quote", ["신체 보호 : 보호복은 불필요합니다.", "신체 보호 : 보호복을 착용하지 않아도 됩니다."])
def test_optional_ppe_field_cannot_create_must(quote):
    doc, draft = technical_case("msds", quote, "보호복을 착용해야 합니다.")
    rejected(run([doc], draft, product_id=PRODUCT_ID), "invalid_evidence")


@pytest.mark.parametrize("quote,accepted", [("보호복을 착용할 것을 권장합니다.", False), ("보호복을 착용할 것이 좋습니다.", False), ("보호복을 착용할 것.", True)])
def test_directive_ending_is_distinct_from_a_recommended_action(quote, accepted):
    doc, draft = technical_case("guide", quote, "보호복을 착용해야 합니다.")
    result = run([doc], draft)
    if accepted:
        assert result.sources and not result.handoff
    else:
        rejected(result, "invalid_evidence")
