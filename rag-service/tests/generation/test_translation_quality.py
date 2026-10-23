"""Synthetic bilingual regressions: preserve identifiers and instruction strength."""
from copy import deepcopy
from datetime import date
import json

import pytest

from rag import prompt, generator
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_msds, synthetic_draft


TRANSLATED_NAMES = {
    'zh': '本资料中的产品名称是교육액-A。',
    'vi': 'Tên sản phẩm trong tài liệu là 교육액-A.',
    'en': 'The product name in this document is 교육액-A.',
    'km': 'ឈ្មោះផលិតផលក្នុងឯកសារនេះគឺ 교육액-A។',
}
INSTRUCTIONS = {
    'zh': '必须佩戴防护手套。',
    'vi': 'Phải đeo găng tay bảo hộ.',
    'en': 'Protective gloves must be worn.',
}


def renamed_fixture(language):
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace('TrainingLiquid-A', '교육액-A')
    draft = synthetic_draft(doc, language)
    statement = draft['statements'][0]
    statement['text'] = TRANSLATED_NAMES[language]
    statement['citations'][0]['quote'] = '제품명: 교육액-A'
    fact = next(f for f in draft['product_facts'] if f['field'] == 'product_name')
    fact['value'] = '교육액-A'
    fact['citations'][0]['quote'] = '제품명: 교육액-A'
    return doc, draft


def run(doc, draft, language):
    before = deepcopy(doc.model_dump())
    result = generator.generate_answer('가상 자료 설명', [doc], language=language,
        product_id=PRODUCT_ID, structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert doc.model_dump() == before
    return result


@pytest.mark.parametrize('language', TRANSLATED_NAMES)
def test_verified_source_product_name_can_remain_korean_in_translated_prose(language):
    doc, draft = renamed_fixture(language)
    result = run(doc, draft, language)
    assert result.sources and TRANSLATED_NAMES[language] in result.answer
    assert result.needs_review and not result.handoff
    assert result.sources[0].chunk_id == doc.metadata['chunk_id']


@pytest.mark.parametrize('language', TRANSLATED_NAMES)
def test_untranslated_explanation_is_not_whitelisted_with_the_product_name(language):
    doc, draft = renamed_fixture(language)
    draft['statements'][0]['text'] += ' 한글 설명을 추가합니다.'
    result = run(doc, draft, language)
    assert not result.sources and result.review_reasons == ['invalid_translation']


def test_unverified_product_name_does_not_gain_script_exception():
    doc, draft = renamed_fixture('vi')
    next(f for f in draft['product_facts'] if f['field'] == 'product_name')['citations'][0]['quote'] = '존재하지 않는 제품명: 교육액-A'
    result = run(doc, draft, 'vi')
    assert not result.sources and result.review_reasons == ['product_unverified']


@pytest.mark.parametrize('language', INSTRUCTIONS)
def test_msds_instruction_translation_keeps_strong_wording_without_claiming_law(language):
    doc = synthetic_msds()
    draft = synthetic_draft(doc, language)
    doc.page_content += '\n보호장갑을 착용하시오.'
    draft['statements'][0]['text'] = INSTRUCTIONS[language]
    draft['statements'][0]['citations'] = [{'chunk_id': doc.metadata['chunk_id'], 'quote': '보호장갑을 착용하시오.'}]
    pid = next(pid for pid, (_, quote) in prompt.critical_passages([doc]).items() if quote == '보호장갑을 착용하시오.')
    draft['critical_translations'].append({'passage_id': pid, 'text': INSTRUCTIONS[language]})
    result = run(doc, draft, language)
    assert result.sources and INSTRUCTIONS[language] in result.answer


@pytest.mark.parametrize('text', [
    'By law, protective gloves must be worn.',
    '法律要求必须佩戴防护手套。',
    'Theo pháp luật, phải đeo găng tay bảo hộ.',
])
def test_msds_instruction_cannot_be_promoted_to_legal_duty(text):
    cid = 'test-msds'
    metadata = {cid: generator.SourceMetadata(doc_type='msds', source_url='https://example.invalid/sds',
                                              chunk_id=cid, doc_id='test', title='test', section='test')}
    citations = [generator.Citation(chunk_id=cid, quote='보호장갑을 착용하시오.')]
    assert generator._invalid_nonlaw_duty(text, citations, metadata)


def test_recommendation_or_unrelated_quote_does_not_license_must():
    cid = 'test-msds'
    metadata = {cid: generator.SourceMetadata(doc_type='msds', source_url='https://example.invalid/sds',
                                              chunk_id=cid, doc_id='test', title='test', section='test')}
    citations = [generator.Citation(chunk_id=cid, quote='보호장갑 착용을 권장합니다.')]
    assert generator._invalid_nonlaw_duty(INSTRUCTIONS['en'], citations, metadata)


def test_general_law_description_is_not_mistaken_for_a_duty_claim():
    assert not generator._invalid_nonlaw_duty('This document describes the purpose of the law.', [], {})


def test_verified_identifier_exception_does_not_disable_number_or_negation_checks():
    assert not prompt.translation_valid('교육액-A 10 ppm 사용 금지', 'Do use 교육액-A at 10%.', 'en', preserved_terms=('교육액-A',))
    assert not prompt.translation_valid('교육액-A 사용 금지', 'Use 교육액-A.', 'en', preserved_terms=('교육액-A',))


@pytest.mark.parametrize('language', TRANSLATED_NAMES)
def test_language_name_glossary_and_identifier_rules_reach_active_prompt(language):
    doc, _ = renamed_fixture(language)
    messages = prompt.build_document_messages('질문', [doc], language=language, as_of=date(2026, 10, 23))
    assert prompt.LANGUAGE_NAMES[language] in messages[0].content
    assert json.dumps(prompt.TRANSLATION_TERMS[language], ensure_ascii=False) in messages[0].content
    assert "'教育液-A'로 바꾸지 마세요" in messages[0].content
    assert '원문의 요구를 단순 권고로 약화' in prompt.VERIFICATION_PROMPT


@pytest.mark.parametrize('language,text,valid', [
    ('en', 'Limited to two virtual training rooms.', True),
    ('en', 'Limited to three virtual training rooms.', False),
    ('vi', 'Chỉ áp dụng cho hai phòng đào tạo giả định.', True),
    ('vi', 'Chỉ áp dụng cho ba phòng đào tạo giả định.', False),
])
def test_natural_location_counts_keep_the_same_value(language, text, valid):
    assert prompt.translation_valid('가상 교육실 2곳에 한정됩니다.', text, language) is valid


@pytest.mark.parametrize('language,text', [('en', 'Use two ppm.'), ('vi', 'Dùng hai ppm.')])
def test_count_word_exception_does_not_convert_measurements(language, text):
    assert not prompt.translation_valid('농도는 2 ppm입니다.', text, language)


def test_common_khmer_exclusion_is_accepted_but_affirmative_is_rejected():
    assert prompt.translation_valid('실제 작업장은 제외합니다.', 'មិនរួមបញ្ចូលទីតាំងការងារពិតប្រាកដទេ។', 'km')
    assert not prompt.translation_valid('실제 작업장은 제외합니다.', 'រួមបញ្ចូលទីតាំងការងារពិតប្រាកដ។', 'km')


def test_khmer_digits_are_comparable_without_allowing_wrong_quantities():
    citation = generator.Citation(chunk_id='test', quote='가상 교육실 2곳에 한정됩니다.')
    assert generator._quantities_supported('បន្ទប់ ២។', [citation])
    assert not generator._quantities_supported('បន្ទប់ ៣។', [citation])


def test_all_warning_ids_are_explicitly_required_in_active_prompt():
    doc = synthetic_msds()
    messages = prompt.build_document_messages('제품명만 설명해줘.', [doc], language='zh', as_of=date(2026, 10, 23))
    for pid in prompt.critical_passages([doc]):
        assert pid in messages[0].content
    assert '이 경고 목록은 생략하지 마세요' in messages[0].content


def test_missing_warning_still_defers_despite_translation_prompt_improvements():
    doc, draft = renamed_fixture('vi')
    draft['critical_translations'].pop()
    result = run(doc, draft, 'vi')
    assert not result.sources and result.review_reasons == ['invalid_translation']


def test_khmer_excluded_and_not_excluded_are_distinct():
    assert prompt.translation_valid('실제 작업장은 제외합니다.', 'កន្លែងធ្វើការពិតត្រូវបានដកចេញ។', 'km')
    assert not prompt.translation_valid('실제 작업장은 제외합니다.', 'កន្លែងធ្វើការពិតមិនត្រូវបានដកចេញ។', 'km')


def test_translated_product_name_is_rejected_even_if_a_mock_verifier_would_accept():
    doc, draft = renamed_fixture('zh')
    draft['statements'][0]['text'] = '产品名称是教育液-A。'
    result = run(doc, draft, 'zh')
    assert not result.sources and result.review_reasons == ['invalid_translation']


@pytest.mark.parametrize('language,text', [('en', 'The document recommends wearing protective gloves.'), ('zh', '建议佩戴防护手套。'), ('vi', 'Tài liệu khuyến nghị đeo găng tay bảo hộ.')])
def test_direct_msds_ppe_instruction_is_not_weakened_to_recommendation(language, text):
    doc = synthetic_msds(); draft = synthetic_draft(doc, language)
    doc.page_content += '\n보호장갑을 착용하시오.'
    draft['statements'][0]['text'] = text
    draft['statements'][0]['citations'] = [{'chunk_id': doc.metadata['chunk_id'], 'quote': '보호장갑을 착용하시오.'}]
    result = run(doc, draft, language)
    assert not result.sources and result.review_reasons == ['invalid_translation']


def test_name_only_duplicate_uses_verified_fact_instead_of_translated_identifier():
    doc, draft = renamed_fixture('zh')
    draft['statements'][0]['conditions'] = []
    draft['statements'][0]['text'] = '产品名称是教育液-A。'
    result = run(doc, draft, 'zh')
    assert result.sources and '教育液-A' not in result.answer
    assert '교육액-A' in result.answer


def test_ppe_duplicate_uses_complete_warning_not_weakened_summary():
    doc = synthetic_msds(); draft = synthetic_draft(doc, 'en')
    doc.page_content += '\n보호장갑을 착용하시오.'
    draft['statements'].append({'kind': 'information', 'text': 'The document advises wearing protective gloves.',
        'citations': [{'chunk_id': doc.metadata['chunk_id'], 'quote': '보호장갑을 착용하시오.'}], 'conditions': []})
    pid = next(pid for pid, (_, q) in prompt.critical_passages([doc]).items() if q == '보호장갑을 착용하시오.')
    draft['critical_translations'].append({'passage_id': pid, 'text': 'Protective gloves must be worn.'})
    result = run(doc, draft, 'en')
    assert result.sources and 'advises wearing' not in result.answer
    assert 'Protective gloves must be worn.' in result.answer
