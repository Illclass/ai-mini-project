"""Synthetic product spans through the production coordinator; no network."""
from copy import deepcopy
from datetime import date
import json

import pytest

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, PRODUCT_LINES, synthetic_msds


class Factory:
    """Deterministic staged provider double; never creates a real client."""
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

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


def fixture():
    doc = synthetic_msds()
    doc.page_content = (
        "[가상 교육액 MSDS | 교육액 | 1. 정보]\n1. 정보\n"
        " 제품명 :\n TrainingLiquid-A\n 제품번호 : DEMO-001\n"
        "함유량 (% w/w)\n TrainingLiquid-A 1.0%\n"
        " 최종 개정일자 : 2026-01-01\n"
        "표지는 청록색입니다."
    )
    candidates = prompt.product_evidence_candidates([doc])
    selections = []
    for field, (value, _) in PRODUCT_LINES.items():
        candidate = next(c for c in candidates if c['field'] == field
                         and (field != 'concentration' or '1.0%' in c['quote']))
        selections.append({'evidence_id': candidate['evidence_id'], 'value': value})
    claim = {'supported': True, 'statements': [{'kind': 'information', 'text': '표지는 청록색입니다.',
             'citations': [{'chunk_id': doc.metadata['chunk_id'], 'quote': '표지는 청록색입니다.'}],
             'conditions': []}], 'product_facts': selections}
    return doc, candidates, claim


def run(doc, claim):
    before = deepcopy(doc.model_dump())
    factory = Factory([claim, claim])
    result = generator.generate_answer('가상 표지를 설명해 주세요.', [doc], product_id=PRODUCT_ID,
        structured_llm=generator._DocumentGenerator('fake', 7, factory=factory),
        language='ko', as_of=date(2026, 10, 24))
    assert doc.model_dump() == before
    return result, factory


def test_production_selects_exact_body_spans_without_copying_or_joining_quotes():
    doc, candidates, claim = fixture()
    result, factory = run(doc, claim)
    assert result.sources and not result.handoff and result.needs_review
    assert set(result.model_dump()) == {'answer', 'sources', 'needs_review', 'handoff'}
    payload = prompt.message_json(factory.calls[0][1], 'PRODUCT_EVIDENCE_CANDIDATES_JSON')
    assert payload == candidates
    assert all(c['quote'] in doc.page_content for c in payload)
    assert all(not c['quote'].startswith('[') for c in payload)
    assert next(c for c in candidates if c['field'] == 'product_number')['quote'] == ' 제품번호 : DEMO-001'
    assert 'TrainingLiquid-A' in result.answer and '1.0%' in result.answer


@pytest.mark.parametrize('field,value', [('product_name', 'TrainingLiquid-B'),
    ('product_number', 'OTHER-999'), ('concentration', '9.0%'), ('revision_date', '2026-10-25')])
def test_real_span_does_not_approve_invented_or_changed_values(field, value):
    doc, candidates, claim = fixture()
    target = next(c['evidence_id'] for c in candidates if c['field'] == field)
    next(s for s in claim['product_facts'] if s['evidence_id'] == target)['value'] = value
    result, _ = run(doc, claim)
    assert result.handoff and result.review_reasons == ['product_unverified'] and not result.sources


def test_unknown_reference_is_rejected_without_accepting_generated_quotes():
    doc, _, claim = fixture()
    claim['product_facts'][0]['evidence_id'] = 'invented-ID'
    result, _ = run(doc, claim)
    assert result.handoff and result.review_reasons == ['product_unverified']


def test_missing_fact_and_other_product_id_still_withhold():
    doc, _, claim = fixture()
    claim['product_facts'].pop()
    assert run(doc, claim)[0].review_reasons == ['product_unverified']
    doc.metadata['product_id'] = 'another-product'
    assert run(doc, claim)[0].review_reasons == ['product_unverified']


def test_wrapped_name_span_is_complete_and_values_are_not_normalized():
    doc, _, _ = fixture()
    doc.page_content = doc.page_content.replace('제품명 :\n TrainingLiquid-A',
        '제품명 :\n TrainingLiquid-A 10\n wt. % in H2O')
    name = next(c for c in prompt.product_evidence_candidates([doc]) if c['field'] == 'product_name')
    assert name['quote'] == ' 제품명 :\n TrainingLiquid-A 10\n wt. % in H2O'
    assert list(prompt.product_name_tokens([doc]).values()) == ['TrainingLiquid-A 10\n wt. % in H2O']


def test_metadata_and_another_chunk_cannot_supply_missing_labels():
    doc, _, _ = fixture()
    doc.page_content = 'TrainingLiquid-A\nDEMO-001\n1.0%\n2026-01-01'
    doc.metadata.update(product_name='TrainingLiquid-A', concentration='1.0%')
    header = deepcopy(doc)
    header.metadata['chunk_id'] = 'header-only'
    header.page_content = '함유량 (% w/w)'
    assert prompt.product_evidence_candidates([doc, header]) == []


def test_non_msds_docs_cannot_create_product_evidence():
    doc, _, _ = fixture()
    doc.metadata['doc_type'] = 'guide'
    assert prompt.product_evidence_candidates([doc]) == []


def test_glossary_mentions_are_not_concentration_headers():
    doc, _, _ = fixture()
    doc.page_content = '기타 약어에 대한 전문\nIC50 - 반수 최대 억제농도; ICAO -\nAldrich- 339741 쪽 18 / 20'
    assert prompt.product_evidence_candidates([doc]) == []


def test_concentration_cannot_include_the_cas_cell_from_the_same_row():
    doc, _, _ = fixture()
    doc.page_content = doc.page_content.replace('TrainingLiquid-A 1.0%',
        'TrainingLiquid-A 7664-93-9 1.0%').replace('함유량 (% w/w)', '화학물질명 CAS 번호 함유량 (% w/w)')
    candidates = prompt.product_evidence_candidates([doc])
    claim = fixture()[2]
    row = next(c for c in candidates if c['field'] == 'concentration')
    fact = next(s for s in claim['product_facts'] if s['evidence_id'] == row['evidence_id'])
    fact['value'] = '7664-93-9 1.0%'
    assert run(doc, claim)[0].review_reasons == ['product_unverified']


def test_internal_selection_does_not_accept_quote_or_metadata_payload():
    with pytest.raises(ValueError):
        generator.ProductFactSelection.model_validate({'evidence_id': 'PFE_1', 'value': 'A',
            'quote': 'made up', 'source_url': 'https://example.invalid'})


def test_product_names_in_warning_translation_are_protected_and_restored_from_source():
    doc, _, claim = fixture()
    warning = '경고: TrainingLiquid-A를 실제 현장 작업에 사용하지 마세요.'
    doc.page_content += '\n' + warning
    claim['statements'][0]['text'] = 'The fictional sign is turquoise.'
    pid = next(iter(prompt.critical_passages([doc])))
    factory = Factory([claim, {'translations': [{'passage_id': pid,
        'text': 'Warning: Do not use CB_PRODUCT_NAME_1 for actual on-site work.'}]}])
    result = generator._DocumentGenerator('fake', 7, factory=factory).invoke(
        prompt.build_document_messages('가상 자료 설명', [doc], language='en', as_of=date(2026, 10, 24)))
    payload = prompt.message_json(factory.calls[1][1], 'UNTRUSTED_TRANSLATION_JSON')
    assert 'CB_PRODUCT_NAME_1' in payload[0]['original']
    assert result.critical_translations[0].text == 'Warning: Do not use TrainingLiquid-A for actual on-site work.'
    assert prompt.critical_passages([doc])[pid][1] == warning


def test_unknown_warning_product_token_cannot_be_restored_or_approved():
    doc, _, claim = fixture()
    doc.page_content += '\n경고: TrainingLiquid-A를 실제 현장 작업에 사용하지 마세요.'
    claim['statements'][0]['text'] = 'The fictional sign is turquoise.'
    pid = next(iter(prompt.critical_passages([doc])))
    bad = {'translations': [{'passage_id': pid, 'text': 'Warning: Do not use CB_PRODUCT_NAME_999 for actual on-site work.'}]}
    factory = Factory([claim, bad, bad])
    with pytest.raises(generator.TranslationGenerationError):
        generator._DocumentGenerator('fake', 7, factory=factory).invoke(
            prompt.build_document_messages('가상 자료 설명', [doc], language='en', as_of=date(2026, 10, 24)))
