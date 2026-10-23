"""Offline Generation regressions; synthetic model output, real date validation."""
from copy import deepcopy
from datetime import date

import pytest

from chembridge_fixtures import PRODUCT_ID, StubLLM, synthetic_msds, synthetic_draft
from rag.generator import _parse_msds_revision_date, generate_answer


def call_with_dates(body_date, metadata_date, *, fact_date=None):
    doc = synthetic_msds()
    draft = synthetic_draft(doc)
    doc.page_content = doc.page_content.replace('2026-01-01', body_date)
    doc.metadata['effective_date'] = metadata_date
    fact = next(f for f in draft['product_facts'] if f['field'] == 'revision_date')
    fact['value'] = body_date if fact_date is None else fact_date
    fact['citations'][0]['quote'] = '개정일: ' + body_date
    before = deepcopy(doc.model_dump())
    result = generate_answer('가상 제품 자료를 설명해줘.', [doc], product_id=PRODUCT_ID,
                             structured_llm=StubLLM(draft), as_of=date(2026, 10, 23))
    assert doc.model_dump() == before
    return result


@pytest.mark.parametrize('body,metadata', [
    ('2026.07.14', '2026-07-14'), ('2026-07-14', '2026-07-14'),
    ('2026.07.14', '2026.07.14'), ('2024.02.29', '2024-02-29'),
])
def test_equivalent_dates_preserve_original_answer_and_metadata(body, metadata):
    result = call_with_dates(body, metadata)
    assert result.sources and result.sources[0].effective_date == metadata
    assert 'MSDS 개정일: ' + body in result.answer
    assert result.review_reasons == ['msds_applicability_unverified']
    assert result.needs_review and not result.handoff


@pytest.mark.parametrize('value', [None, '', '2026-07', '14.07.2026', '07/14/2026',
    '2026.07-14', '2026-07.14', '2026.7.14', '2026.02.30', '2025.02.29',
    '2026.13.01', '2026.00.01', '0000.01.01', '2026.07.14 extra', '2026-07-14T00:00:00'])
def test_parser_rejects_ambiguous_partial_or_impossible_dates(value):
    with pytest.raises(ValueError):
        _parse_msds_revision_date(value)


@pytest.mark.parametrize('body,metadata', [
    ('2026.07.14', '2026-07-15'), ('2026.07.14', None),
    ('2026.07.14', 'invalid'), ('2026.02.30', '2026-02-28'),
    ('2027.01.01', '2027-01-01'),
])
def test_invalid_missing_mismatched_and_future_dates_still_defer(body, metadata):
    result = call_with_dates(body, metadata)
    assert not result.sources and result.needs_review and result.handoff
    assert result.review_reasons == ['product_unverified']


def test_model_must_not_rewrite_value_that_is_not_in_quote():
    result = call_with_dates('2026.07.14', '2026-07-14', fact_date='2026-07-14')
    assert result.review_reasons == ['product_unverified']
    assert not result.sources
