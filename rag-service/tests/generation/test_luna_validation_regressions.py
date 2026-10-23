"""Offline Luna-shaped regressions using synthetic data and mocked semantics.

StubLLM supplies generation output. Generation conftest supplies an always-supported
semantic verifier: these cases test deterministic guards, not actual translation
quality or an actual provider. No API key/network access is needed.
"""
from copy import deepcopy
from datetime import date

import pytest

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds


def run(documents, draft, language):
    before_docs = deepcopy([doc.model_dump() for doc in documents])
    before_draft = deepcopy(draft)
    result = generator.generate_answer(
        "Explain this fictional training document.", documents,
        product_id=PRODUCT_ID, language=language, structured_llm=StubLLM(draft),
        as_of=date(2026, 10, 23),
    )
    assert [doc.model_dump() for doc in documents] == before_docs
    assert draft == before_draft
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    return result


def set_statement(draft, text, cid, quote):
    draft["statements"] = [{"kind": "information", "text": text,
                            "citations": [{"chunk_id": cid, "quote": quote}],
                            "conditions": []}]


def test_vietnamese_negative_copula_is_not_a_legal_duty():
    doc = synthetic_msds()
    quote = "가상 테스트 MSDS입니다. 실제 안전자료가 아닙니다."
    doc.page_content = doc.page_content.replace("가상 테스트 MSDS입니다.", quote)
    draft = synthetic_draft(doc, "vi")
    text = "Đây là MSDS giả định, không phải tài liệu an toàn thực tế."
    set_statement(draft, text, doc.metadata["chunk_id"], quote)
    result = run([doc], draft, "vi")
    assert result.sources and text in result.answer
    assert result.sources[0].chunk_id == doc.metadata["chunk_id"]
    assert result.needs_review and not result.handoff


@pytest.mark.parametrize("text", [
    "Phải đeo kính bảo hộ.",
    "Không phải tài liệu thực tế; phải đeo kính bảo hộ.",
    "Đây không phải tài liệu thực tế. Người đọc phải đeo kính bảo hộ.",
])
def test_negative_copula_exception_does_not_hide_a_real_obligation(text):
    doc = synthetic_msds()
    quote = "이 자료는 실제 문서가 아닙니다. 보안경 착용을 권장합니다."
    draft = synthetic_draft(doc, "vi")
    doc.page_content += "\n" + quote
    set_statement(draft, text, doc.metadata["chunk_id"], quote)
    result = run([doc], draft, "vi")
    assert not result.sources and result.review_reasons == ["invalid_evidence"]


INGREDIENT = "가상성분-B"
ROW = INGREDIENT + " | 1.0%"
INGREDIENT_TEXT = {
    "en": "The document lists 가상성분-B at 1.0%.",
    "vi": "Tài liệu ghi hàm lượng của 가상성분-B là 1.0%.",
    "zh": "资料列出的成分为가상성분-B，含量为1.0%。",
    "km": "ឯកសារបញ្ជាក់ថាសមាសធាតុ 가상성분-B មានកំហាប់ 1.0%។",
}


def ingredient_case(language):
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace(
        "농도: 1.0%", "구성성분 | 함유량 (% w/w)\n" + ROW)
    draft = synthetic_draft(doc, language)
    fact = next(f for f in draft["product_facts"] if f["field"] == "concentration")
    fact["citations"] = [{"chunk_id": doc.metadata["chunk_id"], "quote": ROW}]
    set_statement(draft, INGREDIENT_TEXT[language], doc.metadata["chunk_id"], ROW)
    return doc, draft


@pytest.mark.parametrize("language", INGREDIENT_TEXT)
def test_exact_cited_ingredient_table_row_can_preserve_its_name(language):
    doc, draft = ingredient_case(language)
    result = run([doc], draft, language)
    assert result.sources and INGREDIENT_TEXT[language] in result.answer
    source = result.sources[0]
    assert source.chunk_id == doc.metadata["chunk_id"]
    assert source.source_url == doc.metadata["source_url"]
    assert source.doc_type == "msds"
    assert "1.0%" in result.answer


@pytest.mark.parametrize("language", INGREDIENT_TEXT)
@pytest.mark.parametrize("failure", ["wrong_name", "unquoted_row", "metadata_only", "korean_prose"])
def test_name_script_exception_is_limited_to_exact_cited_table_row(language, failure):
    doc, draft = ingredient_case(language)
    if failure == "wrong_name":
        draft["statements"][0]["text"] = INGREDIENT_TEXT[language].replace(INGREDIENT, "미확인성분-C")
    elif failure == "unquoted_row":
        doc.page_content = doc.page_content.replace(ROW, ROW + "\n다른성분-C | 1.0%")
        draft["statements"][0]["text"] = INGREDIENT_TEXT[language].replace(INGREDIENT, "다른성분-C")
    elif failure == "metadata_only":
        doc.metadata["ingredient_name"] = "메타성분-C"
        draft["statements"][0]["text"] = INGREDIENT_TEXT[language].replace(INGREDIENT, "메타성분-C")
    else:
        draft["statements"][0]["text"] += " 이 문장은 번역되지 않았습니다."
    result = run([doc], draft, language)
    assert not result.sources and result.review_reasons == ["invalid_translation"]


def test_ingredient_name_in_another_chunk_is_not_a_script_exception():
    doc, draft = ingredient_case("en")
    other = synthetic_msds()
    other.metadata["chunk_id"] = "FIXTURE-D1-other-table"
    other.page_content = "구성성분 | 함유량 (% w/w)\n다른성분-C | 1.0%"
    draft["statements"][0]["text"] = INGREDIENT_TEXT["en"].replace(INGREDIENT, "다른성분-C")
    result = run([doc, other], draft, "en")
    assert not result.sources and result.review_reasons == ["invalid_translation"]


@pytest.mark.parametrize("original", ["2026-01-01", "2026.01.01", "2026/01/01"])
@pytest.mark.parametrize("translated", ["January 1, 2026", "1 January 2026"])
def test_complete_equivalent_english_dates_pass_both_guards(original, translated):
    quote = "개정일: " + original
    text = "The revision date is " + translated + "."
    citation = generator.Citation(chunk_id="fictional", quote=quote)
    assert generator._quantities_supported(text, [citation])
    assert prompt.translation_valid(quote, text, "en")


@pytest.mark.parametrize("claim,evidence", [
    ("Revision date: February 1, 2026.", "개정일: 2026-01-02"),
    ("Revision date: January 2, 2026.", "개정일: 2026-02-01"),
    ("Revision date: February 30, 2026.", "개정일: 2026-02-28"),
    ("Revision date: January 2026.", "개정일: 2026-01-01"),
    ("Revision date: 01/02/2026.", "개정일: 2026-02-01"),
    ("Revision date: January 1, 2026abc.", "개정일: 2026-01-01"),
    ("Revision date: 2026-01-01foo.", "개정일: 2026-01-01"),
    ("Revision date: 2026-01-012.", "개정일: 2026-01-01"),
])
def test_changed_invalid_partial_or_ambiguous_english_dates_are_not_equivalent(claim, evidence):
    citation = generator.Citation(chunk_id="fictional", quote=evidence)
    assert not generator._quantities_supported(claim, [citation])
    assert not prompt.translation_valid(evidence, claim, "en")


@pytest.mark.parametrize("text", [
    "Revision date January 1, 2026; concentration 10%.",
    "Revision date January 1, 2026; concentration 20 ppm.",
])
def test_date_normalization_does_not_hide_changed_quantity_or_unit(text):
    quote = "개정일: 2026-01-01. 농도: 10 ppm."
    citation = generator.Citation(chunk_id="fictional", quote=quote)
    assert not generator._quantities_supported(text, [citation])
    assert not prompt.translation_valid(quote, text, "en")


def test_named_date_claim_cannot_be_assembled_from_unrelated_numeric_tokens():
    citation = generator.Citation(chunk_id="fictional", quote="배치번호: 2026. 가상 교육실 1곳. 표본 1개.")
    assert not generator._quantities_supported("Revision date January 1, 2026.", [citation])



@pytest.mark.parametrize("translated,valid", [
    ("កន្លែងធ្វើការពិតមិនត្រូវបានរាប់បញ្ចូលទេ។", True),
    ("មិនរាប់បញ្ចូលកន្លែងធ្វើការពិតប្រាកដទេ។", True),
    ("រាប់បញ្ចូលកន្លែងធ្វើការពិតប្រាកដ។", False),
    ("កន្លែងធ្វើការពិតមិនត្រូវបានដកចេញ។", False),
])
def test_khmer_not_included_remains_distinct_from_included_or_not_excluded(translated, valid):
    assert prompt.translation_valid("실제 작업장은 제외합니다.", translated, "km") is valid
