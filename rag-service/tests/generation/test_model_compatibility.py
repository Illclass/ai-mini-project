"""Offline request-contract checks; these do not measure translation quality."""
from types import SimpleNamespace

import pytest

from rag import generator, llm
from rag.schema import ENV_LLM_MODEL

pytestmark = pytest.mark.claim_verifier


@pytest.mark.parametrize('model', ['gpt-4o', 'gpt-6-luna'])
@pytest.mark.parametrize('stage,schema', [
    ('build_document_llm', generator.ClaimDraft),
    ('build_verification_llm', generator.EvidenceVerification),
])
def test_generation_and_verification_keep_strict_schema_and_luna_compatible_sampling(monkeypatch, model, stage, schema):
    observed = {}
    runnable = SimpleNamespace(invoke=lambda messages: {'supported': False, 'statements': [], 'product_facts': []})

    class Client:
        def with_structured_output(self, actual_schema, **options):
            observed['schema'] = actual_schema
            observed['structured'] = options
            return runnable

    def client(**options):
        observed['client'] = options
        return Client()

    monkeypatch.setattr('langchain_openai.ChatOpenAI', client)
    built = getattr(generator, stage)(model, timeout_seconds=2.5)
    if stage == 'build_document_llm':
        assert isinstance(built, generator._DocumentGenerator)
        assert not built._call(generator.ClaimDraft, []).supported
    else:
        assert built is runnable
    assert observed['schema'] is schema
    assert observed['structured'] == {'method': 'json_schema', 'strict': True}
    assert observed['client']['model'] == model
    assert observed['client']['timeout'] == 2.5
    assert observed['client']['max_retries'] == 0
    assert observed['client']['temperature'] == 0
    if model == 'gpt-6-luna':
        # temperature with Luna's default reasoning setting is rejected by API.
        assert observed['client']['reasoning_effort'] == 'none'
    else:
        assert 'reasoning_effort' not in observed['client']


@pytest.mark.parametrize('model', ['gpt-4o', 'gpt-6-luna'])
def test_plain_text_caller_uses_the_same_model_policy_without_changing_return_type(monkeypatch, model):
    observed = {}

    def create(**options):
        observed.update(options)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=' 답변 '))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, '_client', client)
    monkeypatch.setenv(ENV_LLM_MODEL, model)
    messages = [{'role': 'user', 'content': '가상 테스트'}]
    assert llm.call_llm(messages, timeout=2.5) == '답변'
    assert observed['model'] == model
    assert observed['messages'] == messages
    assert observed['timeout'] == 2.5
    assert observed['temperature'] == 0.2
    if model == 'gpt-6-luna':
        assert observed['reasoning_effort'] == 'none'
    else:
        assert 'reasoning_effort' not in observed
