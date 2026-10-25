"""B direct stabilization: closed GHS rows without bypassing hazard checks."""
from copy import deepcopy

import pytest
from langchain_core.documents import Document

from rag import prompt


def document(text, *, doc_type="msds", section_no=2):
    return Document(page_content=text, metadata={"chunk_id": "B-classification",
                    "doc_type": doc_type, "msds_section_no": section_no})


@pytest.mark.parametrize("text", [
    "금속부식성 물질 : 구분 1\n 급성 독성 (흡입) : 구분 2\n 피부 부식성/피부 자극성 : 구분 1",
    "인화성 액체 : 구분 2",
    "급성 독성 : 구분 3\n(경구)",
    "특정표적장기 독성 - 1 회 노출 : 구분 1 (눈, 중추신경계)",
])
def test_complete_ghs_rows_remain_exact_evidence_without_false_truncation(text):
    doc = document(text)
    before = deepcopy(doc.model_dump())
    assert list(prompt.critical_passages([doc]).values()) == [("B-classification", text)]
    assert prompt.incomplete_critical_chunks([doc]) == set()
    assert doc.model_dump() == before


@pytest.mark.parametrize("text", [
    "금속부식성 물질 : 구분",
    "급성 독성 (흡입) : 구분 2\n환기가 잘 되지 않는 경우",
    "급성 독성 (흡입) : 구분 2\n알 수 없는 항목 : 구분 3",
])
def test_partial_classification_or_open_warning_is_still_blocked(text):
    doc = document(text)
    assert prompt.incomplete_critical_chunks([doc]) == {"B-classification"}
    assert prompt.critical_passages([doc]) == {}


def test_separate_cut_warning_does_not_erase_completed_classification_or_its_block():
    row = "급성 독성 (흡입) : 구분 2"
    doc = document(row + "\n경고: 혼합하지")
    assert prompt.incomplete_critical_chunks([doc]) == {"B-classification"}
    assert list(prompt.critical_passages([doc]).values()) == [("B-classification", row)]


@pytest.mark.parametrize("section_no", [2, 9, 14, 15, 16])
def test_no_msds_section_is_exempt_from_genuine_truncated_warning(section_no):
    doc = document("경고: 다른 물질과 혼합하지", section_no=section_no)
    assert prompt.incomplete_critical_chunks([doc]) == {"B-classification"}


def test_non_msds_table_does_not_receive_ghs_layout_exception():
    doc = document("급성 독성 (흡입) : 구분 2", doc_type="guide")
    assert prompt.incomplete_critical_chunks([doc]) == {"B-classification"}


def test_pdf_page_break_still_splits_and_flags_incomplete_warning():
    doc = document("경고: 다른 물질과 혼합하지\nAldrich- 339741 쪽 3 / 20\n마시오.")
    assert prompt.incomplete_critical_chunks([doc]) == {"B-classification"}
    assert not any("혼합하지\nAldrich" in quote for _, quote in prompt.critical_passages([doc]).values())


def test_prompt_keeps_ppe_claim_context_and_measurement_meaning():
    assert "보호구 표의 명칭만 인용한 경우" in prompt.SYSTEM_PROMPT
    assert "실제 사용·착용 요구 구절도" in prompt.SYSTEM_PROMPT
    assert "이를 안전 작업시간" in prompt.SYSTEM_PROMPT
    assert "숫자가 같아도 다른 주장" in prompt.SYSTEM_PROMPT


LIMITS_UNAVAILABLE = (
    "차. 인화 또는 폭발 범위의 상한/하한\n"
    " 인화 또는 폭발 범위의 상한 / : 자료없음\n"
    " 인화 상한값\n"
    " 인화 또는 폭발 범위의 하한 / : 자료없음\n"
    " 인화 하한값"
)


@pytest.mark.parametrize("status", ["자료없음", "해당없음"])
def test_closed_unavailable_explosion_limits_remain_exact_critical_evidence(status):
    text = LIMITS_UNAVAILABLE.replace("자료없음", status)
    doc = document(text, section_no=9)
    assert list(prompt.critical_passages([doc]).values()) == [("B-classification", text)]
    assert prompt.incomplete_critical_chunks([doc]) == set()


@pytest.mark.parametrize("text", [
    LIMITS_UNAVAILABLE.replace("자료없음", "미확인"),
    LIMITS_UNAVAILABLE.replace("자료없음", "13 %(V)"),
    LIMITS_UNAVAILABLE.replace("인화 또는 폭발 범위의 하한 / : 자료없음\n 인화 하한값", "인화 또는 폭발 범위의 하한 / :"),
    LIMITS_UNAVAILABLE.replace("인화 하한값", "확인되지 않은 다른 항목"),
    LIMITS_UNAVAILABLE + "\n환기가 잘 되지 않는 경우",
    LIMITS_UNAVAILABLE + "\n경고: 혼합하지",
    LIMITS_UNAVAILABLE.replace("하한 / : 자료없음", "하한 / :\nAldrich- 339741 쪽 3 / 20\n자료없음"),
])
def test_unknown_open_numeric_or_page_interrupted_limits_are_not_closed_tables(text):
    assert not prompt._closed_msds_property_table(text, 9)
    assert prompt.incomplete_critical_chunks([document(text, section_no=9)]) == {"B-classification"}


@pytest.mark.parametrize("main,secondary", [("3", None), ("8", "6.1"), ("5.1", "8"), ("1.3", "2.3")])
def test_closed_transport_class_rows_are_exact_critical_evidence(main, secondary):
    text = "다. 운송에서의 위험성 등급 : " + main
    if secondary:
        text += "\n 부차 위험성 : " + secondary
    doc = document(text, section_no=14)
    assert list(prompt.critical_passages([doc]).values()) == [("B-classification", text)]
    assert prompt.incomplete_critical_chunks([doc]) == set()


@pytest.mark.parametrize("text", [
    "다. 운송에서의 위험성 등급 :",
    "다. 운송에서의 위험성 등급 : 10",
    "다. 운송에서의 위험성 등급 : 6.3",
    "다. 운송에서의 위험성 등급 : 3\n 부차 위험성 :",
    "다. 운송에서의 위험성 등급 : 3\n 부차 위험성 : 0",
    "다. 운송에서의 위험성 등급 : 3\n 환기가 잘 되지 않는 경우",
    "다. 운송에서의 위험성 등급 : 3\n 경고: 혼합하지",
    "다. 운송에서의 위험성 등급 : 3\n 부차 위험성 :\n Aldrich- 339741 쪽 3 / 20\n6.1",
])
def test_unknown_or_open_transport_fields_and_page_boundaries_still_block(text):
    assert not prompt._closed_msds_property_table(text, 14)
    assert prompt.incomplete_critical_chunks([document(text, section_no=14)]) == {"B-classification"}


@pytest.mark.parametrize("text,section_no", [(LIMITS_UNAVAILABLE, 14),
    ("다. 운송에서의 위험성 등급 : 3", 9),
    ("다. 운송에서의 위험성 등급 : 3", 15)])
def test_closed_field_exception_requires_matching_actual_section_and_msds_type(text, section_no):
    assert prompt.incomplete_critical_chunks([document(text, section_no=section_no)]) == {"B-classification"}
    assert prompt.incomplete_critical_chunks([document(text, doc_type="guide", section_no=section_no)]) == {"B-classification"}
