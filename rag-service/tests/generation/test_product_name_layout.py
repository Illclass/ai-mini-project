"""Synthetic regressions for MSDS product labels followed by a line break."""
from datetime import date

import pytest
from langchain_core.documents import Document

from rag import generator, prompt
from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_draft, synthetic_msds


@pytest.mark.parametrize('separator', ['\n', '\n ', '\r\n '])
def test_product_name_on_immediately_following_line_is_verified(separator):
    doc = synthetic_msds()
    old = '제품명: TrainingLiquid-A'
    quote = '제품명:' + separator + 'TrainingLiquid-A'
    doc.page_content = doc.page_content.replace(old, quote)
    before = doc.model_dump()
    draft = synthetic_draft(doc)
    draft['statements'][0]['citations'][0]['quote'] = quote
    next(f for f in draft['product_facts'] if f['field'] == 'product_name')['citations'][0]['quote'] = quote
    result = generator.generate_answer('가상 자료 설명', [doc], product_id=PRODUCT_ID,
        structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert prompt.product_name_tokens([doc]) == {'CB_PRODUCT_NAME_1': 'TrainingLiquid-A'}
    assert result.sources and not result.handoff
    assert result.review_reasons == ['msds_applicability_unverified']
    assert doc.model_dump() == before


@pytest.mark.parametrize('following', [
    '제품 번호 : DEMO-001', '브랜드 : Test', '나. 제품의 권고 용도 : 교육용',
    'Product number: DEMO-001', '', '\nTrainingLiquid-A',
])
def test_missing_product_name_does_not_capture_next_field_or_skip_blank_line(following):
    doc = Document(page_content='제품명 :\n ' + following, metadata={'doc_type': 'msds'})
    assert prompt.product_name_tokens([doc]) == {}


def test_wrapped_concentration_suffix_is_part_of_original_name():
    doc = Document(page_content='제품명 :\n TrainingLiquid-A 10\n wt.% in water\n제품 번호 : DEMO-001',
        metadata={'doc_type': 'msds'})
    assert prompt.product_name_tokens([doc]) == {'CB_PRODUCT_NAME_1': 'TrainingLiquid-A 10\n wt.% in water'}


def test_unique_whitespace_variant_is_restored_to_literal_source():
    doc = synthetic_msds()
    doc.page_content = doc.page_content.replace('제품명: TrainingLiquid-A', '제품명:\n TrainingLiquid-A')
    draft = synthetic_draft(doc)
    result = generator.generate_answer('가상 자료 설명', [doc], product_id=PRODUCT_ID,
        structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert result.sources and not result.handoff
    assert 'product_unverified' not in result.review_reasons
