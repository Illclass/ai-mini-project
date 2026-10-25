"""Generation-only regressions: synthetic Documents and mocked model output.

These checks exercise local evidence guards, not real LLM or retrieval quality.
The source text and metadata must remain unchanged after validation.
"""
from copy import deepcopy
from datetime import date
import json

import pytest
from langchain_core.documents import Document

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds


@pytest.fixture(autouse=True)
def no_real_semantic_provider(monkeypatch):
    class SupportedVerifier:
        def invoke(self, messages):
            data = json.loads(messages[1].content.split("\n", 1)[1])
            return {"assessments": [
                {"claim_id": claim["claim_id"], "verdict": "supported"}
                for claim in data["claims"]
            ]}

    monkeypatch.setattr(generator, "build_verification_llm", lambda *args, **kwargs: SupportedVerifier())


def scanner_document(text):
    return Document(page_content=text, metadata={"chunk_id": "SYNTHETIC-TMAH-s1", "doc_type": "msds"})


@pytest.mark.parametrize("contact", [
    "영업시간 - 09:00~18:00, 월요일 – 금요일 (공휴일\n제외)",
    "영업시간 - 09:00~18:00, 월요일 – 금요일 (공휴일\n  제외)\n",
])
def test_wrapped_holiday_contact_tail_is_not_an_incomplete_safety_warning(contact):
    doc = scanner_document("제품명: 가상시험액\n" + contact + "\n경고: 실제 작업에 사용하지 마시오.")
    before = deepcopy(doc.model_dump())
    assert prompt.incomplete_critical_chunks([doc]) == set()
    assert [quote for _, quote in prompt.critical_passages([doc]).values()] == [
        "경고: 실제 작업에 사용하지 마시오."
    ]
    assert doc.model_dump() == before


@pytest.mark.parametrize("text", [
    "제외)",
    "경고: 실제 작업장은\n제외)",
    "영업시간 - 09:00~18:00\n제외)",
    "영업시간 - 09:00~18:00 (공휴일\n경고: 제품 혼합 시 폭발\n제외)",
    "경고: 실제 작업장 (공휴일\n제외)",
])
def test_unrelated_or_dangling_exclusion_tail_still_fails_closed(text):
    doc = scanner_document(text)
    assert prompt.incomplete_critical_chunks([doc]) == {doc.metadata["chunk_id"]}


def technical_case(doc_type, quote, text, *, kind="information"):
    if doc_type == "msds":
        doc = synthetic_msds()
        draft = synthetic_draft(doc)
        doc.page_content += "\n" + quote
    else:
        doc = Document(page_content=quote, metadata={
            "doc_id": "SYNTHETIC-TECH", "doc_type": "guide",
            "law_name": "", "article_no": "", "chunk_id": "SYNTHETIC-TECH:1",
            "title": "가상 교육용 기술지침", "section": "가상 보호복 요구",
            "source_url": "https://example.invalid/fictional-technical-guide",
        })
        draft = {"supported": True, "statements": [], "product_facts": []}
    # Korean warning text is taken directly from the source by the renderer.
    draft["critical_translations"] = []
    draft["statements"] = [{
        "kind": kind, "text": text,
        "citations": [{"chunk_id": doc.metadata["chunk_id"], "quote": quote}],
        "conditions": [],
    }]
    return doc, draft


def run(doc, draft):
    original_document, original_draft = deepcopy(doc.model_dump()), deepcopy(draft)
    result = generator.generate_answer(
        "가상 교육 자료에 적힌 보호복 요구를 설명해 주세요.", [doc],
        structured_llm=StubLLM(draft), as_of=date(2026, 10, 23),
        product_id=PRODUCT_ID if doc.metadata["doc_type"] == "msds" else None,
    )
    assert doc.model_dump() == original_document
    assert draft == original_draft
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    return result


@pytest.mark.parametrize("doc_type", ["guide", "msds"])
@pytest.mark.parametrize("quote", [
    "보호복을 착용하\n여야 한다.",
    "보호복을 착용하\n시오.",
])
@pytest.mark.parametrize("kind", ["information", "recommendation"])
def test_wrapped_source_requirement_keeps_its_force_and_information_category(doc_type, quote, kind):
    text = "제공된 자료에서는 보호복을 착용해야 합니다."
    doc, draft = technical_case(doc_type, quote, text, kind=kind)
    result = run(doc, draft)
    assert result.sources and text in result.answer
    assert result.needs_review is True and result.handoff is False
    assert "자료에 근거한 일반 정보" in result.answer
    assert "권고 지침" not in result.answer
    assert result.sources[0].chunk_id == doc.metadata["chunk_id"]
    assert result.sources[0].source_url == doc.metadata["source_url"]


@pytest.mark.parametrize("doc_type", ["guide", "msds"])
@pytest.mark.parametrize("quote", [
    "보호복을 착용할 것을 권장합니다.",
    "보호복 착용을 권장합니다.",
])
def test_optional_source_advice_must_not_be_strengthened_to_a_requirement(doc_type, quote):
    doc, draft = technical_case(doc_type, quote, "보호복을 반드시 착용해야 합니다.")
    result = run(doc, draft)
    assert result.review_reasons == ["invalid_evidence"]
    assert result.sources == [] and result.needs_review and result.handoff


@pytest.mark.parametrize("doc_type", ["guide", "msds"])
@pytest.mark.parametrize("kind,text", [
    ("legal_obligation", "보호복을 착용해야 합니다."),
    ("information", "법령에 따라 보호복을 착용해야 합니다."),
    ("information", "법적 의무는 아니지만 법에 따라 보호복을 착용해야 합니다."),
])
def test_wrapped_technical_requirement_cannot_be_promoted_to_a_legal_duty(doc_type, kind, text):
    doc, draft = technical_case(doc_type, "보호복을 착용하\n여야 한다.", text, kind=kind)
    result = run(doc, draft)
    if kind == "legal_obligation":
        assert result.sources and not result.handoff
        assert prompt.TEXT['ko']['legal_obligation'] not in result.answer
        assert prompt.TEXT['ko']['information'] in result.answer
    else:
        assert result.review_reasons == ["invalid_evidence"]
        assert result.sources == [] and result.needs_review and result.handoff


@pytest.mark.parametrize("text", [
    "법적 의무라는 뜻은 아니며 이 지침에서는 보호복을 착용해야 합니다.",
    "법적 의무는 아니며 이 지침에서는 보호복을 착용해야 합니다.",
    "법적 의무로 단정하지 않으며 이 지침에서는 보호복을 착용해야 합니다.",
    "This is not a legal obligation; the guide says protective clothing must be worn.",
])
def test_negative_legal_status_does_not_invalidate_a_source_requirement(text):
    doc, draft = technical_case("guide", "보호복을 착용하시오.", text)
    result = run(doc, draft)
    assert result.sources and not result.handoff


@pytest.mark.parametrize("text", [
    "법적 의무라는 뜻은 아니며 법에 따라 보호복을 착용해야 합니다.",
    "This is not a legal obligation; the law says protective clothing must be worn.",
])
def test_negative_disclaimer_cannot_hide_a_separate_affirmative_legal_claim(text):
    doc, draft = technical_case("guide", "보호복을 착용하시오.", text)
    result = run(doc, draft)
    assert result.review_reasons == ["invalid_evidence"] and result.handoff


@pytest.mark.parametrize("footer", [
    "- 2 -\nKOSHA Guide K-1-2023",
    "KOSHA Guide K-1-2023\n- 3 -",
    "- 2 -\nKOSHA GUIDE\nK - 1 - 2023",
])
def test_guide_layout_numbers_are_not_safety_quantities_in_translation(footer):
    original = "(3) 가상 교육실 2곳만 적용합니다.\n" + footer
    translated = "(3) This applies only to 2 virtual training rooms."
    assert prompt.translation_valid(original, translated, "en", source_doc_type="guide")
    assert not prompt.translation_valid(original, translated, "en", source_doc_type="law")
    assert not prompt.translation_valid(original, translated, "en")


@pytest.mark.parametrize("original,translated", [
    ("(3) 농도는 2 ppm입니다.", "The concentration is 2 ppb."),
    ("(3) 가상 교육실 2곳만 적용합니다.", "This applies only to 3 virtual training rooms."),
    ("(3) 혼합하지 마시오.", "You may mix them."),
    ("(3) 개정일은 2026-07-14입니다.", "The revision date is 2026-07-15."),
    ("(2) 명 이상인 경우에만 적용합니다.", "Applies only to workers."),
    ("(2) ppm 이하인 경우에만 적용합니다.", "Applies below the limit."),
    ("(2) workers are required.", "Workers are required."),
    ("- 2 -\n다른 본문", "Other text."),
])
def test_guide_layout_exemption_never_discards_real_quantities_or_warnings(original, translated):
    assert not prompt.translation_valid(original, translated, "en", source_doc_type="guide")


def test_source_supplier_url_in_warning_is_distinct_from_an_invented_url():
    source = "경우는 장갑 공급자(www.example.invalid)에 연락하십시오."
    assert not generator._unsafe_critical_translation(source, source)
    assert generator._unsafe_critical_translation(source.replace("www.example.invalid", "www.evil.invalid"), source)
    assert generator._unsafe_critical_translation(source.replace("www.example.invalid", "www.example.invalid.evil"), source)
    assert generator._unsafe_critical_translation(source + " 현행 법령입니다.", source)
    assert generator._unsafe_text(source)  # General generated prose still forbids URLs.


def test_wrapped_product_percent_line_is_part_of_the_literal_identifier():
    original = "가. 제품명 : FictionalLiquid 10\nwt. % in H2O\n제품 번호 : SYNTHETIC-1"
    doc = scanner_document(original)
    assert prompt.product_name_tokens([doc]) == {"CB_PRODUCT_NAME_1": "FictionalLiquid 10\nwt. % in H2O"}
    assert doc.page_content == original


def test_product_name_does_not_consume_an_unrelated_next_field():
    doc = scanner_document("제품명: FictionalLiquid\n농도: 1.0%\n경고: 실제 작업 금지")
    assert prompt.product_name_tokens([doc]) == {"CB_PRODUCT_NAME_1": "FictionalLiquid"}


@pytest.mark.parametrize("original", [
    "(2) years of storage are allowed.", "(2) seconds is maximum exposure.",
    "(2) 주 이상 보관 금지.", "(2) 년 이상 보관 금지.",
    "(3) 가상 교육실에 한정합니다.",
])
def test_guide_paragraph_numbers_are_never_deleted_by_comparison(original):
    assert prompt.guide_translation_comparison_text(original) == original
    assert not prompt.translation_valid(original, "Storage is limited.", "en", source_doc_type="guide")


def cas_case(body, quote, doc_type="msds"):
    doc = Document(page_content=body, metadata={"doc_type": doc_type, "chunk_id": "SYNTHETIC-CAS"})
    citations = [generator.Citation(chunk_id="SYNTHETIC-CAS", quote=quote)]
    return citations, {"SYNTHETIC-CAS": doc}


def test_cited_valid_cas_is_an_identifier_not_an_impossible_date():
    body = "CAS 번호 / 함유량 (% w/w)\nWater 7732-18-5 >= 90 - < 95"
    citations, docs = cas_case(body, body)
    ids = generator._cited_cas_identifiers(citations, docs)
    assert ids == ("7732-18-5",)
    assert generator._quantities_supported("함유량(% w/w) 표의 값은 >= 90 - < 95입니다.", citations, source_identifiers=ids)
    assert not generator._quantities_supported("함유량(% w/w) 표의 값은 >= 90 - < 99입니다.", citations, source_identifiers=ids)
    assert prompt.calendar_text_with_identifiers("CAS 7732-18-5, 개정일 2026.07.14", ids) == "CAS 7732-18-5, 개정일 2026-07-14"


@pytest.mark.parametrize("body,quote,doc_type", [
    ("CAS 번호 Water 7732-18-6", "Water 7732-18-6", "msds"),
    ("Water 7732-18-5", "Water 7732-18-5", "msds"),
    ("CAS 번호 Water 7732-18-5", "Water 7732-18-5", "guide"),
    ("CAS 번호 Water 7732-18-5", "Water 7732-18-6", "msds"),
])
def test_cas_exemption_requires_source_context_exact_quote_and_checksum(body, quote, doc_type):
    citations, docs = cas_case(body, quote, doc_type)
    assert generator._cited_cas_identifiers(citations, docs) == ()


def test_source_cas_does_not_exempt_an_unrelated_malformed_date():
    assert prompt.calendar_text_with_identifiers("CAS 7732-18-5, 개정일 2026-02-30", ("7732-18-5",)) is None
    assert prompt.calendar_text_with_identifiers("개정일 2026-02-30") is None



def test_a_valid_calendar_date_keeps_date_comparison_even_if_cas_shaped():
    assert prompt.calendar_text_with_identifiers("2026-03-1", ("2026-03-1",)) == "2026-03-01"


def test_cas_mutation_cannot_be_laundered_through_date_comparison():
    body = "CAS 번호 Water 7732-18-5 함유량 90"
    citations, docs = cas_case(body, body)
    ids = generator._cited_cas_identifiers(citations, docs)
    assert not generator._quantities_supported("CAS 번호는 7732-18-6입니다.", citations, source_identifiers=ids)


def test_wrapped_product_name_cannot_be_shortened_before_its_unit_line():
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace("TrainingLiquid-A", "FictionalLiquid 10\nwt. % in H2O")
    draft = synthetic_draft(synthetic_msds())
    name = next(f for f in draft["product_facts"] if f["field"] == "product_name")
    name["value"] = "FictionalLiquid 10"
    name["citations"][0]["quote"] = "제품명: FictionalLiquid 10"
    draft["statements"][0]["text"] = "가상 제품의 제품명은 FictionalLiquid 10입니다."
    draft["statements"][0]["citations"][0]["quote"] = "제품명: FictionalLiquid 10"
    draft["critical_translations"] = []
    result = run(doc, draft)
    assert result.review_reasons == ["product_unverified"] and result.handoff
