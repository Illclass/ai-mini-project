"""Synthetic document-layout regressions. No LLM calls or workplace guidance.

Layout removal must preserve exact evidence spans and genuine safety numbers.
"""
from langchain_core.documents import Document
import pytest

from rag import prompt


def document(body, **metadata):
    defaults = {'chunk_id': 'SYNTH-LAYOUT', 'doc_type': 'guide',
                'title': '안전자료 읽기 안내', 'section': '3. 적용 범위'}
    defaults.update(metadata)
    return Document(page_content=body, metadata=defaults)


def quotes(doc):
    return [quote for _, quote in prompt.critical_passages([doc]).values()]


@pytest.mark.parametrize('warning', [
    '1. 보호장갑을 착용하시오.',
    '12. 보호장갑을 착용하시오.',
    '가. 보호장갑을 착용하시오.',
    '1. 5 ppm 이상이면 적용하지 마십시오.',
    '12. 농도가 1.5% 이상인 경우 사용하지 마십시오.',
])
def test_numbered_full_warning_is_never_discarded_as_section_heading(warning):
    doc = document(warning)
    assert quotes(doc) == [warning]
    assert prompt.incomplete_critical_chunks([doc]) == set()


def test_known_metadata_header_and_repeated_section_are_layout_only():
    warning = '가상 교육실 2곳에만 적용합니다.'
    title, section = '자료 작성 안내 2026', '3. 적용 범위'
    raw = f'[{title} {section}]\n{section}\n{warning}'
    doc = document(raw, title=title, section=section)
    assert quotes(doc) == [warning]
    assert all(quote in raw for quote in quotes(doc))


@pytest.mark.parametrize('repeated', ['3. 적용 범위', '3 적용 범위'])
def test_exact_metadata_section_variant_does_not_turn_into_required_warning(repeated):
    doc = document(repeated + '\n보호구를 착용하시오.')
    assert quotes(doc) == ['보호구를 착용하시오.']


@pytest.mark.parametrize('warning', [
    '[경고: 보호장갑을 착용하시오.]',
    '[주의: 5 ppm 미만인 경우에만 적용합니다.]',
    '[경고 | 보호장갑을 착용하시오.]',
    '[안전 조건 | 5 ppm 미만인 경우에만 적용합니다.]',
])
def test_unknown_bracketed_safety_content_is_not_assumed_metadata(warning):
    doc = document(warning)
    assert quotes(doc) == [warning]
    assert prompt.incomplete_critical_chunks([doc]) == set()


@pytest.mark.parametrize('warning', [
    '경고: 보호장갑을 착용하시오.',
    'P280 보호장갑을 착용하시오.',
    '1. 보호장갑을 착용하시오.',
    'Warning: Do not use metal containers.',
    '警告：不得使用金属容器。',
    'Cảnh báo: Không sử dụng vật chứa bằng kim loại.',
])
def test_explicit_warning_after_glossary_is_not_silently_lost(warning):
    raw = '약어\nABC: 약어 설명\n' + warning
    doc = document(raw)
    assert quotes(doc) == [warning]
    assert prompt.incomplete_critical_chunks([doc]) == set()


@pytest.mark.parametrize('furniture', [
    '- 14 -\nKOSHA GUIDE\nG - 12 - 2013',
    '- 14 -\n\nKOSHA GUIDE\n\nG - 12 - 2013',
    'KOSHA GUIDE\nG - 12 - 2013\n- 14 -',
    'KOSHA GUIDE\n\nG - 12 - 2013\n\n- 14 -',
])
def test_paired_page_furniture_ignored_only_for_comparison_and_spans_stay_exact(furniture):
    warning = '12. 농도가 5 ppm 이상인 경우 사용하지 마십시오.'
    raw = furniture + '\n' + warning
    doc = document(raw)
    extracted = quotes(doc)
    assert extracted
    assert all(quote in raw for quote in extracted)
    comparison = '\n'.join(prompt.guide_translation_comparison_text(q) for q in extracted)
    assert warning in comparison
    assert 'KOSHA GUIDE' not in comparison
    assert 'G - 12 - 2013' not in comparison
    assert '12.' in comparison and '5 ppm' in comparison
    assert prompt.incomplete_critical_chunks([doc]) == set()


@pytest.mark.parametrize('numeric_content', [
    '2. 가상 교육실 2곳에만 적용합니다.',
    '경고: 농도 1.5% 이상이면 적용하지 마십시오.',
    '경고: 5 ppm 미만인 경우에만 적용합니다.',
    '경고: - 14 - 는 이 가상 자료에서 적용 대상 식별자입니다.',
])
def test_real_content_numbers_never_removed_by_footer_comparison(numeric_content):
    doc = document(numeric_content)
    assert quotes(doc) == [numeric_content]
    assert prompt.guide_translation_comparison_text(numeric_content) == numeric_content


def test_truncated_warning_remains_incomplete_after_known_header():
    doc = document('[안전자료 읽기 안내 3. 적용 범위]\n경고: 농도가 5 ppm 이상인 경우')
    assert prompt.incomplete_critical_chunks([doc]) == {doc.metadata['chunk_id']}
    assert quotes(doc) == []


def test_known_contents_page_dotted_leaders_are_not_safety_instructions():
    raw = '목차\n1. 적용 범위 ........ 3\n2. 유해성·위험성 ........ 5\n'
    doc = document(raw, section='목차')
    assert quotes(doc) == []
    assert prompt.incomplete_critical_chunks([doc]) == set()
