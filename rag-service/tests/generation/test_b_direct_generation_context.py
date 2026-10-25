"""Fictional MSDS8 context regressions. No real provider or workplace facts."""
from copy import deepcopy
from datetime import date
import json
import socket

import pytest
from langchain_core.documents import Document
from rag import generator as g
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_msds, synthetic_draft

NOUN = '밀착형 (고글형) 안전안경'
INSTRUCTION = '눈 보호\n: 인증받아 시험을 통과한 눈 보호용 도구 사용.'
BODY = '8. 노출방지 및 개인보호구\n' + INSTRUCTION + '\n' + NOUN + '\n손 보호\n: 보호장갑을 착용하시오.'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('No provider calls are permitted in this offline test')
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def case(body=BODY, section=8, doc_type='msds', text='눈 보호를 위해 밀착형 고글형 안전안경을 사용해야 합니다.'):
    doc = Document(page_content=body, metadata=dict(synthetic_msds().metadata,
        chunk_id='FIXTURE-D1-s8', section='8. 노출방지 및 개인보호구', msds_section_no=section, doc_type=doc_type))
    draft = g.EvidenceDraft(supported=True, statements=[g.EvidenceStatement(kind='information',
        text=text, citations=[g.Citation(chunk_id='FIXTURE-D1-s8', quote=NOUN)], conditions=[])])
    originals = {'FIXTURE-D1-s8': doc}
    metadata = {'FIXTURE-D1-s8': g.SourceMetadata.model_validate(doc.metadata)}
    return doc, draft, originals, metadata


def test_context_addition_preserves_original_noun_and_adds_one_literal_quote():
    doc, draft, originals, metadata = case()
    before = deepcopy((doc.model_dump(), draft.model_dump()))
    result = g._with_exact_ppe_context(draft, originals, metadata)
    citations = result.statements[0].citations
    assert [citation.quote for citation in citations] == [NOUN, INSTRUCTION]
    assert g._verify_citations(citations, originals)
    assert not g._invalid_nonlaw_duty(result.statements[0].text, citations, metadata)
    assert (doc.model_dump(), draft.model_dump()) == before
    assert g._with_exact_ppe_context(result, originals, metadata).model_dump() == result.model_dump()


@pytest.mark.parametrize('fault', [
    'no_action', 'advice_before', 'optional_before', 'optional_after', 'negative_before',
    'exception_after', 'other_part', 'duplicate_heading', 'repeated_noun', 'no_section8',
    'guide', 'information_only',
])
def test_ambiguous_advisory_negated_or_other_scope_never_gets_instruction(fault):
    body, section, doc_type = BODY, 8, 'msds'
    text = '눈 보호를 위해 밀착형 고글형 안전안경을 사용해야 합니다.'
    if fault == 'no_action':
        body = BODY.replace('보호용 도구 사용.', '보호용 도구 목록.')
    elif fault == 'advice_before':
        body = BODY.replace('인증받아', '사용을 권장합니다. 인증받아')
    elif fault == 'optional_before':
        body = BODY.replace('인증받아', '착용은 선택 사항입니다. 인증받아')
    elif fault == 'optional_after':
        body = BODY.replace(INSTRUCTION, INSTRUCTION + '\n착용은 선택 사항입니다.')
    elif fault == 'negative_before':
        body = BODY.replace('인증받아', '사용하지 마세요. 인증받아')
    elif fault == 'exception_after':
        body = BODY.replace(INSTRUCTION, INSTRUCTION + '\n다만, 밀폐형 설비에는 적용하지 않습니다.')
    elif fault == 'other_part':
        body = BODY.replace(NOUN + '\n손 보호', '손 보호\n' + NOUN)
    elif fault == 'duplicate_heading':
        body += '\n눈 보호: 다른 보호용 도구 사용.'
    elif fault == 'repeated_noun':
        body += '\n' + NOUN
    elif fault == 'no_section8':
        section = 7
    elif fault == 'guide':
        doc_type = 'guide'
    else:
        text = '눈 보호 항목에는 밀착형 고글형 안전안경이 기재되어 있습니다.'
    doc, draft, originals, metadata = case(body, section, doc_type, text)
    result = g._with_exact_ppe_context(draft, originals, metadata)
    assert result.model_dump() == draft.model_dump()


def test_recommendation_scope_reference_does_not_cancel_actual_contact_requirement():
    quote = ('이 권고사항은 지정된 목적으로 사용될 경우에만 적용됩니다. '
             '다른 조건에서 사용할 경우 공급자에게 연락하십시오.')
    doc, draft, originals, metadata = case()
    citation = g.Citation(chunk_id=doc.metadata['chunk_id'], quote=quote)
    statement = '이 권고사항은 지정된 목적으로 사용될 경우에만 적용됩니다. 공급자에게 연락해야 합니다.'
    assert not g._weakens_requirement(statement)
    assert g._source_technical_requirement(citation, metadata)
    assert not g._invalid_nonlaw_duty(statement, [citation], metadata)


@pytest.mark.parametrize('advice', ['보안경 착용을 권장합니다.', '착용은 선택 사항입니다.', '착용을 권고합니다.'])
def test_actual_advice_or_optionality_is_not_masked_as_scope_reference(advice):
    doc, draft, originals, metadata = case()
    scope = '이 권고사항은 지정된 목적으로 사용할 경우에만 적용됩니다. '
    citation = g.Citation(chunk_id=doc.metadata['chunk_id'], quote=scope + advice)
    assert g._weakens_requirement(scope + advice)
    assert not g._source_technical_requirement(citation, metadata)
    assert g._invalid_nonlaw_duty('반드시 보안경을 착용해야 합니다.', [citation], metadata)


def test_added_msds_context_never_grants_legal_status():
    doc, draft, originals, metadata = case(text='법에 따라 반드시 밀착형 고글형 안전안경을 사용해야 합니다.')
    result = g._with_exact_ppe_context(draft, originals, metadata)
    assert g._invalid_nonlaw_duty(result.statements[0].text, result.statements[0].citations, metadata)


@pytest.mark.parametrize('corruption', ['number', 'negation'])
def test_context_does_not_override_numeric_or_independent_semantic_rejection(corruption, monkeypatch):
    product = synthetic_msds()
    doc, _, _, _ = case()
    raw = synthetic_draft(product, 'ko')
    text = ('눈 보호용 도구는 999개를 반드시 사용해야 합니다.' if corruption == 'number'
            else '눈 보호용 도구를 사용하지 않아야 합니다.')
    raw['statements'] = [{'kind': 'information', 'text': text, 'conditions': [],
        'citations': [{'chunk_id': doc.metadata['chunk_id'], 'quote': NOUN}]}]
    calls = []
    class RejectingVerifier:
        def invoke(self, messages):
            payload = json.loads(messages[1].content.split('\n', 1)[1]); calls.append(payload)
            return {'assessments': [{'claim_id': claim['claim_id'], 'verdict': 'contradicted'}
                                    for claim in payload['claims']]}
    monkeypatch.setattr(g, 'build_verification_llm', lambda *args, **kwargs: RejectingVerifier())
    result = g.generate_answer('가상 MSDS의 눈 보호 정보', [product, doc],
        product_id=PRODUCT_ID, structured_llm=StubLLM(raw), as_of=date(2026, 10, 25))
    assert result.handoff and not result.sources and result.review_reasons == ['claim_mismatch']
    assert len(calls) == (0 if corruption == 'number' else 2)  # B retains one fully checked correction attempt.



def test_long_eye_quote_with_pdf_footer_keeps_both_literal_spans():
    footer = 'Fictional supplier page 7 / 20\nFictional training document'
    long_quote = INSTRUCTION + '\n' + footer + '\n' + NOUN
    body = '8. 노출방지 및 개인보호구\n' + long_quote + '\n손 보호\n: 보호장갑을 착용하시오.'
    doc, draft, originals, metadata = case(body)
    draft.statements[0].citations[0].quote = long_quote
    result = g._with_exact_ppe_context(draft, originals, metadata)
    assert [citation.quote for citation in result.statements[0].citations] == [long_quote, INSTRUCTION]
    assert g._verify_citations(result.statements[0].citations, originals)


def test_long_quote_crossing_into_another_protection_subsection_is_not_augmented():
    doc, draft, originals, metadata = case()
    draft.statements[0].citations[0].quote = BODY.split('\n', 1)[1]
    result = g._with_exact_ppe_context(draft, originals, metadata)
    assert result.model_dump() == draft.model_dump()


def test_unknown_protection_heading_stops_eye_scope_before_noun():
    for heading in ('귀 보호', '기타 보호'):
        body = '8. 노출방지 및 개인보호구\n' + INSTRUCTION + '\n' + heading + '\n' + NOUN
        doc, draft, originals, metadata = case(body)
        result = g._with_exact_ppe_context(draft, originals, metadata)
        assert result.model_dump() == draft.model_dump(), heading


# Numbered law definitions retain their own and global exceptions.
BODY = '''제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. “교육대상”이란 가상 교육실 이용자를 말한다. 다만, 관람자는 제외한다.
2. “연습대상”이란 가상 연습실 이용자를 말한다. 다만, 방문자는 제외한다.
3. “통합대상”이란 교육대상과 연습대상을 말한다.
'''

@pytest.fixture
def doc():
    return Document(page_content=BODY, metadata={'doc_type':'law'})

def test_other_numbered_definition_exception_not_attached(doc):
    assert not g._law_warning_in_cited_definition(doc, '다만, 방문자는 제외한다.',
        ['“교육대상”이란 가상 교육실 이용자를 말한다.'])

def test_own_exception_kept_even_when_not_in_cited_sentence(doc):
    assert g._law_warning_in_cited_definition(doc, '다만, 관람자는 제외한다.',
        ['“교육대상”이란 가상 교육실 이용자를 말한다.'])

def test_explicit_referenced_term_keeps_its_exception(doc):
    assert g._law_warning_in_cited_definition(doc, '다만, 방문자는 제외한다.',
        ['“통합대상”이란 교육대상과 연습대상을 말한다.'])

def test_global_condition_before_definitions_kept(doc):
    doc.page_content=doc.page_content.replace('다음과 같다.', '다음과 같다. 단, 가상 교육에서만 사용한다.')
    assert g._law_warning_in_cited_definition(doc, '단, 가상 교육에서만 사용한다.',
        ['“교육대상”이란 가상 교육실 이용자를 말한다.'])

@pytest.mark.parametrize('quotes', [[], ['인용에 없는 말'], [BODY[:BODY.index('3. ')]], ['다만, 방문자는 제외한다.']])
def test_ambiguous_or_cross_boundary_spans_keep_warning(doc, quotes):
    assert g._law_warning_in_cited_definition(doc, '다만, 방문자는 제외한다.', quotes)

def test_nondefinition_or_nonlaw_rules_unchanged(doc):
    doc.metadata['doc_type']='guide'
    assert g._law_warning_in_cited_definition(doc, '다만, 방문자는 제외한다.',
        ['“교육대상”이란 가상 교육실 이용자를 말한다.'])


def test_definition_scope_is_applied_to_rendered_and_independently_verified_warnings(monkeypatch):
    doc = Document(page_content=BODY, metadata={
        'law_name': '가상 교육법', 'article_no': '제2조', 'doc_type': 'law',
        'source_url': 'https://example.invalid/synthetic-law', 'chunk_id': 'SYN-LAW-2',
        'effective_date': '2026-01-01'})
    quote = '“교육대상”이란 가상 교육실 이용자를 말한다.'
    raw = {'supported': True, 'statements': [{'kind': 'information', 'text': quote,
        'citations': [{'chunk_id': 'SYN-LAW-2', 'quote': quote}], 'conditions': []}],
        'critical_translations': [], 'product_facts': []}
    seen = []
    class Verifier:
        def invoke(self, messages):
            payload = json.loads(messages[1].content.split('\n', 1)[1]); seen.extend(payload['claims'])
            return {'assessments': [{'claim_id': claim['claim_id'], 'verdict': 'supported'}
                                    for claim in payload['claims']]}
    monkeypatch.setattr(g, 'build_verification_llm', lambda *args, **kwargs: Verifier())
    result = g.generate_answer('가상 교육법 제2조의 교육대상이란 무엇인가요?', [doc],
        topic='law', structured_llm=StubLLM(raw), as_of=date(2026, 10, 25))
    assert result.sources and result.needs_review and not result.handoff
    assert '관람자는 제외한다' in result.answer
    assert '방문자는 제외한다' not in result.answer
    assert any('관람자는 제외한다' in claim['text'] for claim in seen)
    assert not any('방문자는 제외한다' in claim['text'] for claim in seen)
    assert 'law_currentness_unverified' in result.review_reasons
