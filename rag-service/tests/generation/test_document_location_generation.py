"""Synthetic MSDS location-only regressions. Providers are mocked, no network."""
from copy import deepcopy
from datetime import date
import json

import pytest
from langchain_core.documents import Document

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, PRODUCT_LINES, StubLLM, synthetic_msds


QUESTIONS = {
    'ko': '사고가 난 상황은 아닙니다. 눈 접촉 응급조치 내용이 있는 MSDS 항목과 출처만 알려 주세요. 처치 방법은 설명하지 마세요.',
    'zh': '目前没有发生事故。请只指出MSDS中眼睛接触急救信息所在的章节和出处，不要说明处置步骤。',
    'vi': 'Hiện không có tai nạn. Chỉ cho tôi mục và nguồn trong MSDS về sơ cứu khi tiếp xúc mắt, không hướng dẫn xử trí.',
    'en': 'There is no incident. Identify only the section and source for eye-contact first-aid information in the MSDS; do not give treatment steps.',
    'km': 'មិនមានគ្រោះថ្នាក់កើតឡើងទេ។ សូមប្រាប់តែផ្នែក និងប្រភពក្នុង MSDS ដែលមានព័ត៌មានសង្គ្រោះបឋមពេលប៉ះភ្នែក។ កុំប្រាប់ជំហានព្យាបាល។',
}


class Factory:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    def __call__(self, schema, model, **options):
        outer = self
        class Client:
            def invoke(self, messages):
                outer.calls.append((schema, messages, options))
                value = outer.outputs.pop(0)
                if isinstance(value, Exception):
                    raise value
                return deepcopy(value)
        return Client()


def documents():
    identity = synthetic_msds()
    first_aid = Document(page_content=(
        '4. 응급조치 요령\n'
        ' 가. 눈에 들어갔을 때 : 다량의 물로 씻어내십시오.\n'
        ' 나. 피부에 접촉했을 때 : 즉시 물로 씻으십시오.\n'
        ' 중화하려고 하지 마십시오.'), metadata={**identity.metadata,
        'chunk_id': 'FIXTURE-D1-s4', 'section': '4. 응급조치 요령', 'msds_section_no': 4})
    storage = Document(page_content='7. 취급 및 저장방법\n금속 용기를 사용하지 말 것.',
        metadata={**identity.metadata, 'chunk_id': 'FIXTURE-D1-s7',
                  'section': '7. 취급 및 저장방법', 'msds_section_no': 7})
    return [identity, first_aid, storage]


def selection(docs, number=4):
    item = next(c for c in prompt.msds_location_candidates(docs) if c['section_no'] == number)
    candidates = prompt.product_evidence_candidates(docs)
    facts = [{'evidence_id': next(c['evidence_id'] for c in candidates if c['field'] == field), 'value': value}
             for field, (value, _) in PRODUCT_LINES.items()]
    return {'supported': True, 'location_ids': [item['location_id']], 'product_facts': facts}


def run(docs, outputs, language='km', **kwargs):
    before = deepcopy([d.model_dump() for d in docs])
    factory = Factory(outputs)
    result = generator.generate_answer(QUESTIONS[language], docs, language=language,
        product_id=PRODUCT_ID, as_of=date(2026, 10, 24),
        structured_llm=generator._DocumentGenerator('fake', 7, factory=factory), **kwargs)
    assert [d.model_dump() for d in docs] == before
    return result, factory


@pytest.mark.parametrize('language', QUESTIONS)
def test_only_section_and_actual_source_are_returned_in_all_supported_languages(language):
    docs = documents()
    result, factory = run(docs, [selection(docs)], language)
    assert not result.handoff and result.needs_review
    assert prompt.msds_location_text(4, language) in result.answer
    assert '씻' not in result.answer and '중화' not in result.answer and 'wash' not in result.answer
    assert result.answer.endswith('[1]')
    assert len(result.sources) == 1 and result.sources[0].chunk_id == 'FIXTURE-D1-s4'
    for field in ('law_name', 'article_no', 'source_url', 'doc_type', 'chunk_id'):
        assert getattr(result.sources[0], field) == docs[1].metadata.get(field, '')
    assert result.sources[0].section == '4. 응급조치 요령'
    assert set(result.model_dump()) == {'answer', 'sources', 'needs_review', 'handoff'}
    assert len(factory.calls) == 1 and factory.calls[0][0] is generator.DocumentLocationDraft
    payload = prompt.message_json(factory.calls[0][1], 'UNTRUSTED_LOCATION_SELECTION_JSON')
    encoded = json.dumps(payload, ensure_ascii=False)
    assert '눈에 들어갔을 때' in encoded and '다량의 물' not in encoded and '씻어내' not in encoded


@pytest.mark.parametrize('bad', ['unknown_id', 'duplicate_id', 'free_text'])
def test_model_cannot_invent_a_section_duplicate_it_or_supply_treatment_prose(bad):
    docs = documents()
    output = selection(docs)
    if bad == 'unknown_id':
        output['location_ids'] = ['MSDS_LOC_999']
    elif bad == 'duplicate_id':
        output['location_ids'] *= 2
    else:
        output['answer'] = 'Wash your eyes now.'
    result, _ = run(docs, [output])
    assert result.handoff and not result.sources
    assert result.review_reasons == ['invalid_output' if bad == 'free_text' else 'invalid_evidence']
    assert 'Wash your eyes' not in result.answer


@pytest.mark.parametrize('kind', ['metadata_only', 'duplicate', 'wrong_number', 'wrong_title'])
def test_unverified_body_heading_is_not_a_location_candidate(kind):
    doc = documents()[1]
    if kind == 'metadata_only':
        doc.page_content = doc.page_content.split('\n', 1)[1]
    elif kind == 'duplicate':
        doc.page_content += '\n4. 응급조치 요령'
    elif kind == 'wrong_number':
        doc.metadata['msds_section_no'] = 7
    else:
        doc.metadata['section'] = '4. 저장방법'
    assert prompt.msds_location_candidates([doc]) == []


def test_absent_heading_returns_no_evidence_without_an_llm_call():
    docs = documents()[:2]
    docs[1].page_content = docs[1].page_content.split('\n', 1)[1]
    result, factory = run(docs, [])
    assert result.handoff and result.review_reasons == ['no_evidence'] and not factory.calls


@pytest.mark.parametrize('field,value', [('product_name', 'WrongLiquid'), ('product_number', 'OTHER-999'),
    ('concentration', '9.0%'), ('revision_date', '2026-10-25')])
def test_location_request_still_requires_real_product_identity_values(field, value):
    docs = documents()
    output = selection(docs)
    candidates = prompt.product_evidence_candidates(docs)
    eid = next(c['evidence_id'] for c in candidates if c['field'] == field)
    next(f for f in output['product_facts'] if f['evidence_id'] == eid)['value'] = value
    result, _ = run(docs, [output, output])
    assert result.handoff and not result.sources and result.review_reasons == ['product_unverified']


def test_cross_product_retrieval_and_incomplete_warning_context_still_withhold():
    docs = documents()
    docs[1].metadata['product_id'] = 'another-product'
    assert run(docs, [])[0].review_reasons == ['product_unverified']
    docs = documents()
    docs[1].page_content += '\n다른 물질과 혼합한 경우,'
    result, factory = run(docs, [])
    assert result.handoff and result.review_reasons == ['incomplete_warning_context'] and not factory.calls


@pytest.mark.claim_verifier
def test_independent_semantic_rejection_of_wrong_location_is_not_overridden(monkeypatch):
    docs = documents()
    seen = []
    class Verifier:
        def invoke(self, messages):
            payload = json.loads(messages[1].content.split('\n', 1)[1])
            seen.append(payload)
            assert payload['documents'][1]['page_content'] == docs[1].page_content
            return {'assessments': [{'claim_id': c['claim_id'], 'verdict': 'unsupported'} for c in payload['claims']]}
    monkeypatch.setattr(generator, 'build_verification_llm', lambda *a, **k: Verifier())
    result, factory = run(docs, [selection(docs, 7), selection(docs, 7)])
    assert result.handoff and result.review_reasons == ['claim_mismatch'] and not result.sources
    assert len(seen) == 2 and len(factory.calls) == 2


@pytest.mark.claim_verifier
def test_verifier_unavailable_is_not_treated_as_location_success(monkeypatch):
    class Verifier:
        def invoke(self, messages):
            raise TimeoutError('SECRET')
    monkeypatch.setattr(generator, 'build_verification_llm', lambda *a, **k: Verifier())
    docs = documents()
    result, factory = run(docs, [selection(docs)])
    assert result.handoff and result.review_reasons == ['verification_unavailable']
    assert len(factory.calls) == 1 and 'SECRET' not in result.answer


def test_old_or_injected_provider_cannot_smuggle_procedure_text_into_location_path():
    docs = documents()
    picks = selection(docs)
    facts = generator._resolve_product_selections(
        [generator.ProductFactSelection(**f) for f in picks['product_facts']], prompt.product_evidence_candidates(docs))
    candidate = prompt.msds_location_candidates(docs)[0]
    draft = generator.EvidenceDraft(supported=True, statements=[generator.EvidenceStatement(
        kind='information', text='다량의 물로 씻어내십시오.', conditions=[],
        citations=[generator.Citation(**c) for c in candidate['citations']])], product_facts=facts)
    result = generator.generate_answer(QUESTIONS['km'], docs, language='km', product_id=PRODUCT_ID,
        as_of=date(2026, 10, 24), structured_llm=StubLLM(draft))
    assert result.handoff and result.review_reasons == ['invalid_evidence'] and not result.sources


@pytest.mark.parametrize('language,incident', [('ko', '황산이 지금 눈에 튀었어요.'),
    ('zh', '化学品溅到我的眼睛了。'), ('vi', 'Tôi hít phải khí.'),
    ('en', 'I inhaled acid vapor.'), ('km', 'ឥឡូវនេះ ខ្ញុំពិបាកដកដង្ហើម។')])
def test_actual_incident_still_precedes_explicit_location_only_request(language, incident):
    factory = Factory([])
    result = generator.generate_answer(incident + ' ' + QUESTIONS[language], [], language=language,
        structured_llm=generator._DocumentGenerator('fake', 7, factory=factory))
    assert result.handoff and result.review_reasons == ['emergency'] and not factory.calls


@pytest.mark.parametrize('question', ['황산 보관 시 어떤 용기를 사용해야 하나요?',
    'What PPE is needed? Please give a source.', 'តើរកព័ត៌មានសម្ភារៈធុងសម្រាប់ការផ្ទុកនៅឯណា?'])
def test_ordinary_information_questions_keep_full_generation_and_warning_policy(question):
    assert not prompt.msds_location_only_question(question)


def test_location_provider_timeout_is_sanitized_and_not_retried():
    docs = documents()
    result, factory = run(docs, [TimeoutError('SECRET')])
    assert result.handoff and result.review_reasons == ['llm_timeout']
    assert len(factory.calls) == 1 and 'SECRET' not in result.answer
