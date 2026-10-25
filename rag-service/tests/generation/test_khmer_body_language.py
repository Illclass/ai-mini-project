"""Synthetic mixed-script corrections; semantic verdicts explicitly mocked."""
from copy import deepcopy
from datetime import date
import json

import pytest
from langchain_core.documents import Document
from rag import generator, prompt
from test_product_evidence_selection import Factory


BAD = 'ស្លាកពណ៌青។'
GOOD = 'ស្លាកពណ៌បៃតងខៀវ។'


def fixture():
    doc = Document(page_content='표지는 청록색입니다.', metadata={
        'doc_id': 'KM-FIXTURE', 'chunk_id': 'KM-FIXTURE-s1', 'doc_type': 'guide',
        'title': '가상 색상 자료', 'section': '색상', 'law_name': '', 'article_no': '',
        'source_url': 'https://example.invalid/khmer-fixture'})
    claim = {'supported': True, 'statements': [{'kind': 'information', 'text': BAD,
        'citations': [{'chunk_id': 'KM-FIXTURE-s1', 'quote': doc.page_content}],
        'conditions': []}], 'product_facts': []}
    return doc, claim


def translated(text=GOOD, pid='s0'):
    return {'translations': [{'passage_id': pid, 'text': text}]}


def run(doc, factory):
    return generator.generate_answer('ពណ៌ស្លាកជាអ្វី?', [doc], language='km',
        structured_llm=generator._DocumentGenerator('fake', 7, factory=factory),
        as_of=date(2026, 10, 24))


def test_mixed_script_gets_one_dedicated_correction_without_changing_citations():
    doc, claim = fixture()
    before = deepcopy(doc.model_dump())
    factory = Factory([claim, translated()])
    result = run(doc, factory)
    assert result.sources and not result.handoff and GOOD in result.answer and '青' not in result.answer
    assert len(factory.calls) == 2
    payload = prompt.message_json(factory.calls[1][1], 'UNTRUSTED_BODY_TRANSLATION_JSON')
    assert payload[0]['original'] == BAD
    assert payload[0]['citations'] == claim['statements'][0]['citations']
    assert doc.model_dump() == before


def test_valid_khmer_does_not_add_a_translation_call():
    doc, claim = fixture()
    claim['statements'][0]['text'] = GOOD
    factory = Factory([claim])
    assert not run(doc, factory).handoff and len(factory.calls) == 1


@pytest.mark.parametrize('output', [translated(BAD), translated('中文'), translated(''),
    translated(pid='invented'), {'translations': []},
    {'translations': [{'passage_id': 's0', 'text': GOOD}, {'passage_id': 's0', 'text': GOOD}]}])
def test_failed_repair_stays_withheld_without_script_bypass(output):
    doc, claim = fixture()
    factory = Factory([claim, output, output])
    result = run(doc, factory)
    assert result.handoff and not result.sources and result.review_reasons == ['invalid_translation']
    assert len(factory.calls) == 3


def test_correction_cannot_drop_source_number():
    doc, claim = fixture()
    doc.page_content = '가상 표지는 2개입니다.'
    claim['statements'][0]['citations'][0]['quote'] = doc.page_content
    claim['statements'][0]['text'] = BAD + ' 2'
    assert run(doc, Factory([claim, translated(), translated()])).review_reasons == ['invalid_translation']


@pytest.mark.claim_verifier
def test_fluent_but_wrong_meaning_still_fails_independent_verification(monkeypatch):
    doc, claim = fixture()
    wrong = 'ស្លាកពណ៌ក្រហម។'
    factory = Factory([claim, translated(wrong), claim, translated(wrong)])
    class Contradicted:
        def invoke(self, messages):
            data = json.loads(messages[1].content.split('\n', 1)[1])
            return {'assessments': [{'claim_id': c['claim_id'], 'verdict': 'contradicted'} for c in data['claims']]}
    monkeypatch.setattr(generator, 'build_verification_llm', lambda *a, **k: Contradicted())
    result = run(doc, factory)
    assert result.handoff and not result.sources
    assert len([c for c in factory.calls if c[0] is generator.TranslationBatch]) == 2


def test_unsupported_citation_is_not_sent_to_language_repair():
    doc, claim = fixture()
    claim['statements'][0]['citations'][0]['quote'] = 'not in source'
    factory = Factory([claim, claim])
    result = run(doc, factory)
    assert result.handoff and result.review_reasons == ['invalid_evidence']
    assert all(c[0] is generator.ClaimDraft for c in factory.calls)


def test_khmer_uses_korean_grounding_then_translation_and_one_failed_translation_correction():
    doc, claim = fixture()
    claim['statements'][0]['text'] = doc.page_content
    factory = Factory([claim, translated(BAD), translated()])
    result = run(doc, factory)
    assert result.sources and not result.handoff and GOOD in result.answer
    assert '본문·조건은 반드시 한국어' in factory.calls[0][1][0].content
    assert 'previous translation failed' in factory.calls[2][1][0].content
    for call in factory.calls[1:]:
        assert prompt.message_json(call[1], 'UNTRUSTED_BODY_TRANSLATION_JSON')[0]['original'] == doc.page_content


def test_body_provider_timeout_still_fails_closed_without_retry():
    doc, claim = fixture()
    factory = Factory([claim, TimeoutError('SECRET')])
    result = run(doc, factory)
    assert result.review_reasons == ['llm_timeout'] and result.handoff
    assert 'SECRET' not in result.answer and len(factory.calls) == 2


@pytest.mark.parametrize('weak', [
    'សូមណែនាំមិនឱ្យប្រើធុងដែក។',
    'សូមណែនាំឱ្យចាក់សោរដោយមាំមួន។',
    'គួរតែប្រើស្រោមដៃ។',
])
def test_khmer_advice_is_recognized_as_weaker_than_requirement(weak):
    assert generator._weakens_requirement(weak)
    assert not generator._weakens_requirement('មិនត្រូវប្រើធុងដែក។')


def product_case(text):
    from test_product_evidence_selection import fixture as product_fixture
    doc, _, claim = product_fixture()
    quote = '금속 용기를 사용하지 말 것.'
    doc.page_content += '\n' + quote
    claim['statements'][0].update(text=text, citations=[{'chunk_id': doc.metadata['chunk_id'], 'quote': quote}])
    warning = {'translations': [{'passage_id': pid, 'text': 'មិនត្រូវប្រើធុងដែក។'}
                               for pid in prompt.critical_passages([doc])]}
    return doc, claim, warning


def test_product_name_is_protected_before_translation_and_restored_only_after_validation():
    from chembridge_fixtures import PRODUCT_ID
    doc, claim, warning = product_case('TrainingLiquid-A는 금속 용기를 사용하지 말 것.')
    bad = translated('មិនត្រូវប្រើធុងដែកសម្រាប់ផលិតផលដែលបានបកប្រែឈ្មោះ។')
    good = translated('មិនត្រូវប្រើធុងដែកសម្រាប់ CB_PRODUCT_NAME_1។')
    factory = Factory([claim, bad, good, warning])
    result = generator.generate_answer('가상 자료의 보관 금지를 설명해 주세요.', [doc], language='km',
        product_id=PRODUCT_ID, structured_llm=generator._DocumentGenerator('fake', 7, factory=factory),
        as_of=date(2026, 10, 24))
    assert not result.handoff and 'TrainingLiquid-A' in result.answer
    assert 'CB_PRODUCT_NAME' not in result.answer
    data = prompt.message_json(factory.calls[1][1], 'UNTRUSTED_BODY_TRANSLATION_JSON')
    assert 'CB_PRODUCT_NAME_1' in data[0]['original'] and 'TrainingLiquid-A' not in data[0]['original']


def test_khmer_translation_cannot_weaken_a_real_source_requirement():
    from chembridge_fixtures import PRODUCT_ID
    doc, claim, _ = product_case('금속 용기를 사용하지 말 것.')
    weak = translated('សូមណែនាំមិនឱ្យប្រើធុងដែក។')
    factory = Factory([claim, weak, weak])
    result = generator.generate_answer('가상 자료의 보관 금지를 설명해 주세요.', [doc], language='km',
        product_id=PRODUCT_ID, structured_llm=generator._DocumentGenerator('fake', 7, factory=factory),
        as_of=date(2026, 10, 24))
    assert result.handoff and result.review_reasons == ['invalid_translation'] and not result.sources


def test_weakened_korean_pivot_is_not_sent_to_the_translator():
    doc, claim, _ = product_case('금속 용기를 사용하지 않도록 권장합니다.')
    factory = Factory([claim])
    result = generator._DocumentGenerator('fake', 7, factory=factory).invoke(
        prompt.build_document_messages('가상 자료 질문', [doc], language='km', as_of=date(2026, 10, 24)))
    assert result.statements[0].text.endswith('권장합니다.')
    assert len(factory.calls) == 1  # Outer validation/repair owns this invalid draft.


def test_bad_quote_does_not_hide_specialist_action_from_repair_diagnostics():
    from test_product_evidence_selection import fixture as product_fixture
    doc, _, claim = product_fixture()
    doc.metadata.update(section='4. 응급조치 요령', msds_section_no=4)
    action = '눈에 들어갔을 때 다량의 물로 씻어내십시오.'
    doc.page_content += '\n' + action
    claim['statements'][0].update(text=action, citations=[{'chunk_id': doc.metadata['chunk_id'],
                                                       'quote': 'not a contiguous source quote'}])
    factory = Factory([claim])
    assembled = generator._DocumentGenerator('fake', 7, factory=factory).invoke(
        prompt.build_document_messages('문서 위치만 알려 주세요.', [doc], language='km', as_of=date(2026, 10, 24)))
    diagnostics = generator._draft_repair_feedback(assembled, [doc], reason='invalid_evidence', language='km')
    codes = {issue['code'] for issue in diagnostics['issues']}
    assert {'quote_not_contiguous', 'specialist_response_action_not_answer'} <= codes
    assert len(factory.calls) == 1
