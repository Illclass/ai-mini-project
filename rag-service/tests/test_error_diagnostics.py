"""B diagnostic regressions: synthetic exceptions/documents, no provider calls."""
import json
import logging
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import RateLimitError

from app import main
from rag import diagnostics, generator
from rag.schema import RagRequest, RagResponse, TOPIC_LAW


def provider_error(code='credit_balance_exhausted', status=429):
    response = httpx.Response(status, request=httpx.Request('POST', 'https://api.openai.com/v1/chat/completions'),
                              headers={'x-request-id': 'req_SYNTHETIC', 'retry-after': '12'})
    return RateLimitError('SECRET_API_KEY JWT PRIVATE_QUESTION', response=response,
                          body={'code': code, 'type': 'insufficient_quota',
                                'message': 'SECRET_API_KEY JWT PRIVATE_QUESTION'})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, 'latency_stats', main.LatencyStatistics())
    main.app.dependency_overrides[main.get_current_user] = lambda: {'sub': 'SYNTHETIC'}
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def request(client):
    return client.post('/rag-query', json=RagRequest(question='PRIVATE_QUESTION', topic=TOPIC_LAW).model_dump())


@pytest.mark.parametrize('code', ['credit_balance_exhausted', 'project_spend_limit_exceeded',
    'organization_usage_limit_exceeded', 'rate_limit_exceeded', 'slow_down', 'future_structured_error'])
def test_provider_details_preserve_machine_codes_without_raw_secrets(code):
    result = diagnostics.exception_details(provider_error(code), stage='generation')
    assert result['category'] == 'provider_error'
    assert result['provider_status'] == 429 and result['provider_code'] == code
    assert result['provider_request_id'] == 'req_SYNTHETIC'
    assert result['retry_after_seconds'] == '12'
    assert not any(x in json.dumps(result) for x in ['SECRET_API_KEY', 'JWT', 'PRIVATE_QUESTION'])


def test_unsafe_provider_fields_are_not_logged_or_reflected():
    result = diagnostics.provider_details(429, {'error': {'code': 'sk-secret', 'type': 'Bearer secret',
        'message': 'PRIVATE_QUESTION'}}, {'x-request-id': 'JWT.secret', 'retry-after': 'secret'})
    assert result == {'category': 'provider_error', 'provider_status': 429}


def test_capture_is_request_local_and_resets_after_exceptions():
    with diagnostics.capture_failures() as outer:
        diagnostics.record_failure(provider_error(), stage='generation')
        with pytest.raises(RuntimeError), diagnostics.capture_failures() as inner:
            diagnostics.record_failure(diagnostics.ExperimentStopped('provider_halted'), stage='chain')
            raise RuntimeError('SYNTHETIC')
        assert len(inner) == len(outer) == 1
        assert outer[0]['category'] == 'provider_error'
    with diagnostics.capture_failures() as fresh:
        assert fresh == []


def test_provider_failure_has_safe_headers_and_original_error_json(client, monkeypatch, caplog):
    def fail(req):
        diagnostics.record_failure(provider_error(), stage='generation')
        raise generator.GenerationUnavailable('PRIVATE_QUESTION SECRET_API_KEY')
    monkeypatch.setattr(main, 'answer', fail)
    with caplog.at_level(logging.INFO):
        response = request(client)
    assert response.status_code == 503
    assert response.json() == {'detail': '잠시 후 다시 시도해 주세요.'}
    assert response.headers['X-ChemBridge-Outcome'] == 'provider_error'
    assert response.headers['X-ChemBridge-Provider-Code'] == 'credit_balance_exhausted'
    assert response.headers['X-ChemBridge-Provider-Status'] == '429'
    safe_logs = '\n'.join(r.getMessage() for r in caplog.records if r.name.startswith('chembridge.'))
    assert 'provider_error' in safe_logs and 'credit_balance_exhausted' in safe_logs
    assert not any(s in safe_logs + response.text for s in ['PRIVATE_QUESTION', 'SECRET_API_KEY', 'JWT'])
    assert response.headers['X-ChemBridge-Request-Id'] in safe_logs


def test_experiment_stop_never_calls_provider_and_is_not_quota_error(client, monkeypatch):
    provider = Mock(side_effect=AssertionError('No model call permitted'))
    def stopped(req):
        raise diagnostics.ExperimentStopped('provider_halted')
    monkeypatch.setattr(main, 'answer', stopped)
    monkeypatch.setattr(generator, 'build_document_llm', provider)
    response = request(client)
    assert response.status_code == 503
    assert response.headers['X-ChemBridge-Outcome'] == 'experiment_stopped'
    assert response.headers['X-ChemBridge-Reason'] == 'provider_halted'
    assert 'X-ChemBridge-Provider-Status' not in response.headers
    provider.assert_not_called()


@pytest.mark.parametrize('reason,category', [
    ('invalid_evidence', 'verification_failed'), ('claim_mismatch', 'verification_failed'),
    ('invalid_translation', 'verification_failed'), ('incomplete_warning_context', 'verification_failed'),
    ('no_evidence', 'insufficient_evidence'), ('retrieval_empty', 'insufficient_evidence'),
    ('verification_unavailable', 'verifier_unavailable'), ('product_unverified', 'product_unverified'),
])
def test_normal_200_deferrals_keep_body_contract_but_expose_reason(client, monkeypatch, reason, category):
    result = generator.GenerationAPIResponse(answer='가상 보류 안내', sources=[], needs_review=True, handoff=True, latency_ms=0)
    result._review_reasons = [reason]
    monkeypatch.setattr(main, 'answer', lambda req: result)
    response = request(client)
    assert response.status_code == 200
    assert set(response.json()) == set(RagResponse.model_fields)
    assert response.json()['sources'] == [] and response.json()['handoff'] is True
    assert response.headers['X-ChemBridge-Outcome'] == category
    assert response.headers['X-ChemBridge-Reason'] == reason


def test_normal_answer_and_caution_are_not_reported_as_validation_failures(client, monkeypatch):
    for review, expected in [(False, 'answer'), (True, 'review_required')]:
        result = RagResponse(answer='가상 정상 답변', sources=[], needs_review=review, handoff=False)
        monkeypatch.setattr(main, 'answer', lambda req: result)
        response = request(client)
        assert response.status_code == 200
        assert response.headers['X-ChemBridge-Outcome'] == expected


def test_real_generation_adapter_retains_stop_classification(client, monkeypatch):
    hit = {'text': '가상 표지의 색상은 청록색입니다.', 'metadata': {
        'doc_id': 'SYNTH', 'doc_type': 'guide', 'law_name': '', 'article_no': '',
        'chunk_id': 'SYNTH-1', 'source_url': 'https://example.invalid/source'}}
    fake = Mock(); fake.invoke.side_effect = diagnostics.ExperimentStopped('provider_halted')
    monkeypatch.setattr(main, 'answer', lambda req: generator.generate(req.question, [hit], 'ko', structured_llm=fake))
    response = request(client)
    assert response.headers['X-ChemBridge-Outcome'] == 'experiment_stopped'
    assert response.status_code == 503 and fake.invoke.call_count == 1


def test_real_citation_rejection_stays_held_without_provider_call(client, monkeypatch):
    hit = {'text': '가상 표지의 색상은 청록색입니다.', 'metadata': {
        'doc_id': 'SYNTH', 'doc_type': 'guide', 'law_name': '', 'article_no': '',
        'chunk_id': 'SYNTH-1', 'source_url': 'https://example.invalid/source'}}
    fake = Mock(); fake.invoke.return_value = {'supported': True, 'statements': [{
        'kind': 'information', 'text': '가상 표지의 색상은 빨간색입니다.',
        'citations': [{'chunk_id': 'SYNTH-1', 'quote': '가상 표지의 색상은 빨간색입니다.'}], 'conditions': []}]}
    verifier = Mock(side_effect=AssertionError('Invalid quotes must fail before provider verification'))
    monkeypatch.setattr(generator, 'build_verification_llm', verifier)
    monkeypatch.setattr(main, 'answer', lambda req: generator.generate(req.question, [hit], 'ko', structured_llm=fake))
    response = request(client)
    assert response.status_code == 200
    assert response.headers['X-ChemBridge-Outcome'] == 'verification_failed'
    assert response.json()['sources'] == [] and response.json()['handoff'] is True
    assert '빨간색' not in response.json()['answer']
    verifier.assert_not_called()


def test_verifier_provider_error_is_not_misreported_as_missing_evidence(client, monkeypatch, caplog):
    hit = {'text': '가상 표지의 색상은 청록색입니다.', 'metadata': {
        'doc_id': 'SYNTH', 'doc_type': 'guide', 'law_name': '', 'article_no': '',
        'chunk_id': 'SYNTH-1', 'source_url': 'https://example.invalid/source'}}
    fake = Mock(); fake.invoke.return_value = {'supported': True, 'statements': [{
        'kind': 'information', 'text': hit['text'],
        'citations': [{'chunk_id': 'SYNTH-1', 'quote': hit['text']}], 'conditions': []}]}
    verifier = Mock(); verifier.invoke.side_effect = provider_error('project_spend_limit_exceeded')
    monkeypatch.setattr(generator, 'build_verification_llm', lambda *a, **k: verifier)
    monkeypatch.setattr(main, 'answer', lambda req: generator.generate(req.question, [hit], 'ko', structured_llm=fake))
    with caplog.at_level(logging.INFO):
        response = request(client)
    assert response.status_code == 200  # Preserve existing verification-outage policy.
    assert response.headers['X-ChemBridge-Outcome'] == 'provider_error'
    assert response.headers['X-ChemBridge-Provider-Code'] == 'project_spend_limit_exceeded'
    assert response.json()['sources'] == [] and response.json()['handoff'] is True
    assert fake.invoke.call_count == verifier.invoke.call_count == 1
    assert '"stage": "verification"' in caplog.text
