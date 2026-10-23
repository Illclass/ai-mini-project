"""Generation-only warning extraction; synthetic quotes, no real LLM calls."""
from copy import deepcopy
from datetime import date

import pytest
from langchain_core.documents import Document

from rag.prompt import critical_passages, incomplete_critical_chunks
from rag.generator import generate_answer
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_msds, synthetic_draft


def document(text, cid='test-warning'):
    return Document(page_content=text, metadata={'chunk_id': cid, 'doc_type': 'msds'})


def test_wrapped_prohibition_and_condition_are_exact_contiguous_quotes():
    text = '경고: 미스트/증기를 흡입하지\n마시오.\n환기가 잘 되지 않는 경우\n호흡기 보호구를 착용하시오.'
    doc = document(text)
    before = deepcopy(doc.model_dump())
    quotes = [q for _, q in critical_passages([doc]).values()]
    assert quotes == ['경고: 미스트/증기를 흡입하지\n마시오.', '환기가 잘 되지 않는 경우\n호흡기 보호구를 착용하시오.']
    assert all(q in text for q in quotes)
    assert not incomplete_critical_chunks([doc])
    assert doc.model_dump() == before


def test_contact_disclaimer_and_glossary_do_not_become_warnings():
    doc = document('영업시간 - 09:00~18:00\n(공휴일 제외)\n'
                   '위 정보는 정확하다고 여겨지지만 모든 것을 포괄하 지는\n않으며, 안내서 정도로만 사용되어져야 함. '
                   '이 문서의 정보는 현재 알려진 지식에 근거하며\n제품에 적용가능함.\n'
                   '기타 약어에 대한 전문\nIBC - 화학적 위험물 운송 선박의 구조와 장비에 관한 코드; ICAO -\n국제민간항공기구')
    assert critical_passages([doc]) == {}
    assert not incomplete_critical_chunks([doc])


@pytest.mark.parametrize('text', [
    '경고: 이 물질을 다른 물질과 혼합하지',
    '며\n규정된 목적으로 사용될 경우에만\n적용됩니다.',
    '경고: 혼합하면\nAldrich- 339741 쪽 3 / 20\n폭발할 수 있습니다.',
])
def test_truncated_or_page_interrupted_warning_is_flagged(text):
    doc = document(text)
    assert incomplete_critical_chunks([doc]) == {'test-warning'}
    assert not any(q.endswith('혼합하지') for _, q in critical_passages([doc]).values())


@pytest.mark.parametrize('text', [
    'H314 피부에 심한 화상과 눈에 손상을 일으킴.',
    'H330 흡입하면 치명적임.',
    'P284 [환기가 잘 되지 않는 경우] 호흡기 보호구를 착용하시오.',
    '농도 1.0% 이상인 경우에만 적용됩니다.',
    'Do not mix with other products.',
    '禁止混合使用。',
    'Không được trộn với sản phẩm khác.',
])
def test_actual_hazards_conditions_numbers_and_multilingual_prohibitions_survive(text):
    doc = document(text)
    assert [q for _, q in critical_passages([doc]).values()] == [text]
    assert not incomplete_critical_chunks([doc])


def test_unfinished_warning_never_reaches_provider():
    doc = synthetic_msds()
    doc.page_content += '\n경고: 혼합하면'
    llm = StubLLM(error=AssertionError('must defer before model call'))
    result = generate_answer('자료를 설명해줘.', [doc], product_id=PRODUCT_ID,
                             structured_llm=llm, as_of=date(2026, 10, 23))
    assert not llm.calls and not result.sources
    assert result.needs_review and result.handoff
    assert result.review_reasons == ['incomplete_warning_context']


def test_display_joins_soft_breaks_without_rewriting_citation_evidence():
    doc = synthetic_msds()
    draft = synthetic_draft(doc)
    doc.page_content = doc.page_content.replace('실제 현장 작업에', '실제 현장\n작업에')
    # Korean warning display comes directly from source; omit optional translations.
    draft['critical_translations'] = []
    before = deepcopy(doc.model_dump())
    result = generate_answer('자료를 설명해줘.', [doc], product_id=PRODUCT_ID,
                             structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert result.sources
    assert '경고: 이 자료를 실제 현장 작업에 사용하지 마세요.' in result.answer
    assert doc.model_dump() == before


def test_no_punctuation_prohibition_is_not_discarded():
    doc = document('금속 용기를 사용하지 말 것')
    assert [q for _, q in critical_passages([doc]).values()] == ['금속 용기를 사용하지 말 것']
    assert not incomplete_critical_chunks([doc])


def test_composition_table_is_not_an_incomplete_warning():
    doc = document('3. 구성성분의 명칭 및 함유량\n단일물질/혼합물\n: 단일물질\n함유량 (% w/w)\nSulfuric acid 7664-93-9 >= 95 - <= 100')
    assert not critical_passages([doc])
    assert not incomplete_critical_chunks([doc])


def test_korean_list_marker_is_not_a_sentence():
    doc = document('나. 금속 용기를 사용하지\n마시오.')
    assert [q for _, q in critical_passages([doc]).values()] == ['나. 금속 용기를 사용하지\n마시오.']


def test_bracketed_warning_is_not_mistaken_for_generated_document_header():
    doc = document('[경고: 혼합 금지]')
    assert [q for _, q in critical_passages([doc]).values()] == ['[경고: 혼합 금지]']
    assert not incomplete_critical_chunks([doc])
