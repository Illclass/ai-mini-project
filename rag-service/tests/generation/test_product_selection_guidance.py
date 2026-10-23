"""Generation-only product selection guidance; no network calls or frontend edits."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from rag import chain, llm
from rag.generator import generate_answer, generate
from rag.prompt import TEXT
from rag.schema import LANGUAGES, TOPIC_CHEMICAL, RagRequest
from chembridge_fixtures import PRODUCT_ID, StubLLM, hit, synthetic_msds


@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('question', ['보호구는?', 'Wet Bench에서 어떤 보호구를 착용하나요?'])
def test_unspecified_product_requests_selection_without_model_calls(monkeypatch, language, question):
    factory = Mock(side_effect=AssertionError('Product selection must not call LLM'))
    monkeypatch.setattr(llm, 'build_structured_llm', factory)
    doc = synthetic_msds()
    before = deepcopy(doc.model_dump())
    result = generate_answer(question, [doc], language=language, topic=TOPIC_CHEMICAL)
    assert result.answer == TEXT[language]['product_selection_required']
    assert result.review_reasons == ['product_unverified']
    assert result.sources == [] and result.needs_review and result.handoff
    assert set(result.model_dump()) == {'answer', 'sources', 'needs_review', 'handoff'}
    assert doc.model_dump() == before
    factory.assert_not_called()


def test_wet_bench_request_reaches_guidance_through_unchanged_chain(monkeypatch):
    retrieve = Mock(return_value=[hit(synthetic_msds())])
    monkeypatch.setattr(chain, 'retrieve', retrieve)
    response = chain.answer(RagRequest(question='보호구는?', topic=TOPIC_CHEMICAL,
                                       equipment_id='DEMO-WET-01'))
    assert retrieve.call_args.kwargs['equipment_id'] == 'DEMO-WET-01'
    assert response.answer.startswith('어떤 약품인지 선택해 주세요.')
    assert response.sources == [] and response.needs_review and response.handoff
    assert set(response.model_dump()) == {'answer', 'sources', 'needs_review', 'handoff', 'latency_ms'}


def test_selected_but_wrong_product_keeps_existing_confirmation_message():
    response = generate('보호구는?', [hit(synthetic_msds())], 'ko',
                        product_id='different-product', topic=TOPIC_CHEMICAL)
    assert response.answer == TEXT['ko']['product_unverified']
    assert response.sources == [] and response.needs_review and response.handoff


def test_selected_product_reaches_generation_instead_of_selection_message():
    provider = StubLLM({'supported': False, 'statements': []})
    response = generate('보호구는?', [hit(synthetic_msds())], 'ko', product_id=PRODUCT_ID,
                        topic=TOPIC_CHEMICAL, structured_llm=provider)
    assert len(provider.calls) == 1
    assert response.answer == TEXT['ko']['no_evidence']


def test_emergency_still_takes_priority_over_product_selection():
    response = generate('Wet Bench에서 약품이 작업복에 튀었어요.', [hit(synthetic_msds())], 'ko', topic=TOPIC_CHEMICAL)
    assert response.answer == TEXT['ko']['emergency']
    assert response.sources == [] and response.needs_review and response.handoff
