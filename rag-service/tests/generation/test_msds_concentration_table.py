"""Offline Generation regression: table labels belong to the cited value chunk."""
from copy import deepcopy
from datetime import date

import pytest

from rag.generator import generate_answer
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds


def case(header='함유량 (% w/w)', row='Sulfuric acid 7664-93-9 >= 95 - <= 100',
         value='>= 95 - <= 100', quote=None):
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace('농도: 1.0%', header + '\n' + row)
    draft = synthetic_draft(doc)
    fact = next(f for f in draft['product_facts'] if f['field'] == 'concentration')
    fact['value'] = value
    fact['citations'] = [{'chunk_id': doc.metadata['chunk_id'], 'quote': row if quote is None else quote}]
    return doc, draft, fact


def run(documents, draft):
    before = deepcopy([d.model_dump() for d in documents])
    result = generate_answer('가상 제품 자료를 설명해줘.', documents, product_id=PRODUCT_ID,
                             structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert [d.model_dump() for d in documents] == before
    return result


@pytest.mark.parametrize('header', ['함유량 (% w/w)', '농도 (%)', 'Concentration (%)', '浓度 (%)', 'nồng độ (%)'])
def test_table_header_in_same_chunk_accepts_verbatim_row(header):
    doc, draft, _ = case(header=header)
    result = run([doc], draft)
    assert result.sources
    assert '농도: >= 95 - <= 100' in result.answer
    assert result.sources[0].chunk_id == doc.metadata['chunk_id']
    assert result.review_reasons == ['msds_applicability_unverified']
    assert result.needs_review and not result.handoff


@pytest.mark.parametrize('cite_header_too', [False, True])
def test_label_in_another_chunk_does_not_qualify_value(cite_header_too):
    doc, draft, fact = case(header='구성성분')
    other = synthetic_msds()
    other.page_content = '함유량 (% w/w)'
    other.metadata['chunk_id'] = 'FIXTURE-D1-table-header'
    if cite_header_too:
        fact['citations'].append({'chunk_id': other.metadata['chunk_id'], 'quote': other.page_content})
    result = run([doc, other], draft)
    assert not result.sources and result.review_reasons == ['product_unverified']


def test_metadata_label_is_not_source_body_evidence():
    doc, draft, _ = case(header='구성성분')
    doc.metadata['column_label'] = '함유량'
    result = run([doc], draft)
    assert not result.sources and result.review_reasons == ['product_unverified']


@pytest.mark.parametrize('row,value,quote', [
    ('Sulfuric acid 95%', '95%', 'Sulfuric acid'),
    ('Sulfuric acid 95%', '50%', 'Sulfuric acid 95%'),
    ('Sulfuric acid 195%', '95%', 'Sulfuric acid 195%'),
    ('Sulfuric acid 95%', '95', 'Sulfuric acid 95%'),
    ('Sulfuric acid >= 95 - <= 100', '95-100%', 'Sulfuric acid >= 95 - <= 100'),
    ('Sulfuric acid 95%', '95%', '함유량: Sulfuric acid 95%'),
])
def test_missing_changed_partial_values_and_invented_quotes_are_rejected(row, value, quote):
    doc, draft, _ = case(row=row, value=value, quote=quote)
    result = run([doc], draft)
    assert not result.sources and result.review_reasons == ['product_unverified']


def test_product_name_still_requires_label_inside_its_quote():
    doc, draft, _ = case()
    fact = next(f for f in draft['product_facts'] if f['field'] == 'product_name')
    fact['citations'][0]['quote'] = 'TrainingLiquid-A'
    result = run([doc], draft)
    assert not result.sources and result.review_reasons == ['product_unverified']
