"""Synthetic offline source-layout tests; these are not real LLM quality tests.

Real permitted team MSDS fixtures are checked separately in the local audit
artifact. No PDF, index, credentials or private absolute paths are required here.
"""
from copy import deepcopy

import pytest
from langchain_core.documents import Document
from rag import prompt


FOOTER = ('SIGALD- 999999 쪽 17 / 18\n'
          'The life science business of Merck operates as MilliporeSigma in\n'
          'the US and Canada')
NFPA = 'NFPA:\n인화성\n3\n건강 불안정\n2 0\n특수 위험성'


def document(text):
    return Document(page_content=text, metadata={
        'doc_type': 'msds', 'chunk_id': 'SYNTHETIC:16', 'msds_section_no': 16,
        'product_id': 'synthetic-product'})


def test_explicit_glossary_survives_exact_supplier_footer_and_wrapped_terms():
    text = ('최종 개정일자 : 2026.01.15\n'
            '기타 약어에 대한 전문\n'
            'ACGIH : 가상 노출 기준\n' + FOOTER + '\n'
            'KR OEL : 가상 노출기준설정 대상 유해인자\n'
            'AIIC - 가상 재고; ASTM - 가상 표준; IMO -')
    doc = document(text)
    before = deepcopy(doc.model_dump())
    assert prompt.incomplete_critical_chunks([doc]) == set()
    assert prompt.critical_passages([doc]) == {}
    assert doc.model_dump() == before


@pytest.mark.parametrize('warning', [
    'H314 피부에 접촉할 경우',
    '경고: 피부에 접촉할 경우',
    'warning: exposure above 20% may',
])
def test_real_cut_warning_after_glossary_and_footer_still_blocks(warning):
    doc = document('기타 약어에 대한 전문\nABC - 가상 약어\n' + FOOTER + '\n' + warning)
    assert prompt.incomplete_critical_chunks([doc]) == {'SYNTHETIC:16'}


@pytest.mark.parametrize('warning', [
    'H314 심한 피부 화상을 일으킴',
    '경고: 20% 이상에서는 사용하지 마시오.',
    'warning: do not use above 20%.',
])
def test_complete_warning_after_glossary_is_preserved_exactly(warning):
    doc = document('기타 약어에 대한 전문\nABC - 가상 약어\n' + FOOTER + '\n' + warning)
    assert prompt.incomplete_critical_chunks([doc]) == set()
    assert warning in [quote for _, quote in prompt.critical_passages([doc]).values()]


def test_page_footer_outside_glossary_cannot_exempt_cut_warning():
    doc = document(FOOTER + '\nH314 피부에 접촉할 경우')
    assert prompt.incomplete_critical_chunks([doc]) == {'SYNTHETIC:16'}


@pytest.mark.parametrize('ratings', ['3 2 0', '0 0 0', '4 4 4', '1 2 3'])
def test_complete_nfpa_table_is_a_critical_passage_with_all_ratings(ratings):
    fire, health, instability = ratings.split()
    text = f'NFPA:\n인화성\n{fire}\n건강 불안정\n{health} {instability}\n특수 위험성'
    doc = document(text)
    assert prompt.incomplete_critical_chunks([doc]) == set()
    assert list(prompt.critical_passages([doc]).values()) == [('SYNTHETIC:16', text)]


@pytest.mark.parametrize('text', [
    'NFPA:\n인화성\n3\n건강 불안정\n2\n특수 위험성',
    'NFPA:\n인화성\n3\n건강 불안정\n2 8\n특수 위험성',
    'NFPA:\n인화성\n3\n건강 불안정\n2 0 1\n특수 위험성',
    'NFPA:\n인화성\n3\n건강 불안정\n2 0\n특수 위험성\n경우',
    'NFPA:\n인화성\n3\n건강 불안정\n2 0\n특수 위험성\n경고: 접촉한 경우',
])
def test_incomplete_invalid_or_appended_warning_nfpa_still_blocks(text):
    assert prompt.incomplete_critical_chunks([document(text)]) == {'SYNTHETIC:16'}


def test_nfpa_before_a_separate_cut_coded_warning_does_not_hide_the_warning():
    doc = document(NFPA + '\nH314 피부에 접촉할 경우')
    assert prompt.incomplete_critical_chunks([doc]) == {'SYNTHETIC:16'}
    assert ('SYNTHETIC:16', NFPA) in prompt.critical_passages([doc]).values()


def test_nfpa_numbers_remain_subject_to_translation_validation():
    doc = document(NFPA)
    original = next(iter(prompt.critical_passages([doc]).values()))[1]
    assert prompt.translation_valid(original,
        'NFPA: Flammability 3, health 2, instability 0, special hazards.', 'en')
    assert not prompt.translation_valid(original,
        'NFPA: Flammability 3, health 1, instability 0, special hazards.', 'en')
    assert not prompt.translation_valid(original, 'NFPA: hazardous material.', 'en')
