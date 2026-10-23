"""Synthetic MSDS regressions; these are not workplace instructions."""
from datetime import date
import json

import pytest

from rag import generator
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds

CONTACT = '다른 물질과 혼합하여 사용하는 경우에는 장갑 공급자에게 연락하십시오.'
REFERENCE = '권장 보관온도 : 제품 라벨을 참조.'
STORAGE = '금속 용기를 사용하지 말 것. 단단히 잠글 것.'


def case(quote, text, conditions=None):
    doc = synthetic_msds()
    draft = synthetic_draft(doc)
    doc.page_content += '\n' + quote
    citation = {'chunk_id': doc.metadata['chunk_id'], 'quote': quote}
    draft['statements'] = [{'kind': 'information', 'text': text,
        'citations': [citation], 'conditions': [
            {'text': condition, 'citations': [dict(citation)]} for condition in (conditions or [])]}]
    draft['critical_translations'] = []  # Korean warnings are rendered from the source.
    return doc, draft


def run(doc, draft):
    return generator.generate_answer('가상 자료의 내용을 설명해 주세요.', [doc],
        product_id=PRODUCT_ID, structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))


def test_conditional_supplier_contact_preserves_action_and_condition():
    doc, draft = case(CONTACT, '다른 물질과 혼합하여 사용하는 경우 장갑 공급자에게 연락하도록 되어 있습니다.',
        ['다른 물질과 혼합하여 사용하는 경우에 해당합니다.'])
    before = doc.model_dump()
    result = run(doc, draft)
    assert result.sources and not result.handoff
    assert '다른 물질과 혼합' in result.answer and '장갑 공급자에게 연락' in result.answer
    assert result.needs_review
    assert doc.model_dump() == before


@pytest.mark.claim_verifier
@pytest.mark.parametrize('text,conditions', [
    ('승인된 보호장갑의 사용을 권장합니다.', []),
    ('항상 장갑 공급자에게 연락해야 합니다.', []),
    ('장갑 공급자에게 연락하도록 되어 있습니다.', ['모든 취급 상황에 해당합니다.']),
])
def test_contact_does_not_become_selection_or_lose_conditions(monkeypatch, text, conditions):
    doc, draft = case(CONTACT, text, conditions)
    observed = []
    class RejectChangedMeaning:
        def invoke(self, messages):
            payload = json.loads(messages[1].content.split('\n', 1)[1])
            observed.append(payload)
            return {'assessments': [{'claim_id': c['claim_id'], 'verdict': 'unsupported'}
                                    for c in payload['claims']]}
    monkeypatch.setattr(generator, 'build_verification_llm', lambda *a, **kw: RejectChangedMeaning())
    result = run(doc, draft)
    assert observed and observed[0]['claims'][0]['citations'][0]['quote'] == CONTACT
    assert result.review_reasons == ['claim_mismatch']
    assert result.handoff and not result.sources


def test_storage_reference_is_information_and_actual_prohibition_keeps_force():
    doc, draft = case(REFERENCE, '자료의 권장 보관온도 항목에는 제품 라벨 참조로 기재되어 있습니다.')
    doc.page_content += '\n' + STORAGE
    draft['statements'].append({'kind': 'information',
        'text': '자료에서는 금속 용기를 사용하지 말고 단단히 잠가 보관하도록 합니다.',
        'citations': [{'chunk_id': doc.metadata['chunk_id'], 'quote': STORAGE}], 'conditions': []})
    result = run(doc, draft)
    assert result.sources and not result.handoff
    assert '제품 라벨 참조' in result.answer and '금속 용기를 사용하지 말고' in result.answer
    assert result.needs_review


def test_reference_cannot_be_promoted_to_mandatory_requirement():
    doc, draft = case(REFERENCE, '반드시 제품 라벨을 참조해야 합니다.')
    result = run(doc, draft)
    assert result.review_reasons == ['invalid_evidence']
    assert result.handoff and not result.sources


def test_missing_storage_temperature_is_not_invented():
    doc, draft = case(REFERENCE, '보관온도는 4도입니다.')
    result = run(doc, draft)
    assert result.review_reasons == ['claim_mismatch']
    assert result.handoff and not result.sources


def test_source_instruction_cannot_be_turned_into_mere_advice():
    doc, draft = case('보호장갑을 착용하시오.', '보호장갑 착용을 권장합니다.')
    result = run(doc, draft)
    assert result.review_reasons == ['invalid_translation']
    assert result.handoff and not result.sources


def test_source_instruction_is_not_promoted_to_legal_obligation():
    doc, draft = case(STORAGE, '법에 따라 반드시 금속 용기를 사용하지 않아야 합니다.')
    result = run(doc, draft)
    assert result.review_reasons == ['invalid_evidence']
    assert result.handoff and not result.sources


def test_changed_quote_is_rejected_before_semantic_verification():
    doc, draft = case(CONTACT, '다른 물질과 혼합하여 사용하는 경우 장갑 공급자에게 연락하도록 되어 있습니다.')
    draft['statements'][0]['citations'][0]['quote'] = '모든 경우에는 장갑 공급자에게 연락하십시오.'
    result = run(doc, draft)
    assert result.review_reasons == ['invalid_evidence']
    assert result.handoff and not result.sources
