"""Generation-owned contract checks: mock Documents/LLM, no real API success claim."""
from copy import deepcopy
import ast
from pathlib import Path
from datetime import date
import json

import httpx
import pytest
from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from openai import APITimeoutError

from rag.generator import generate_answer

AS_OF = date(2026, 10, 22)


class FakeLLM:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        if self.error is not None:
            raise self.error
        return deepcopy(self.output)


@pytest.fixture
def guide():
    return Document(
        page_content=(
            "실제 안전 지침이 아닌 가상 테스트 문서입니다. "
            "교육실 안내에 한하여 적용합니다. "
            "표지를 청록색으로 표시할 것을 권고합니다."
        ),
        metadata={
            "law_name": "", "article_no": "", "doc_type": "guide",
            "source_url": "https://example.invalid/fictional-guide",
            "chunk_id": "fixture-guide:1", "article_title": "가상 안내자료",
            "paragraph": "제1항", "producer_note": {"retain": "all metadata"},
        },
    )


@pytest.fixture
def law():
    return Document(
        page_content=(
            "실제 법령이 아닌 가상 테스트 조문입니다. "
            "가상 교육실 운영자에게 적용합니다. "
            "가상 교육실 운영자는 기록을 17일간 보관하여야 합니다."
        ),
        metadata={
            "law_name": "가상테스트법(실제 법령 아님)", "article_no": "제999조",
            "doc_type": "law", "source_url": "https://example.invalid/fictional-law",
            "chunk_id": "fixture-law:999:1", "article_title": "가상 기록",
            "effective_date": "2001-01-01", "paragraph": "제1항",
        },
    )


def citation(document, quote):
    return {"chunk_id": document.metadata["chunk_id"], "quote": quote}


def guide_statement(guide):
    return {
        "kind": "recommendation",
        "text": "제공된 안내자료는 표지를 청록색으로 표시할 것을 권고합니다.",
        "citations": [citation(guide, "표지를 청록색으로 표시할 것을 권고합니다.")],
        "conditions": [{
            "text": "교육실 안내에 한하여 적용합니다.",
            "citations": [citation(guide, "교육실 안내에 한하여 적용합니다.")],
        }],
    }


def law_statement(law):
    return {
        "kind": "legal_obligation",
        "text": "제공된 가상 법령 자료에는 기록을 17일간 보관하도록 규정되어 있습니다.",
        "citations": [citation(law, "가상 교육실 운영자는 기록을 17일간 보관하여야 합니다.")],
        "conditions": [{
            "text": "가상 교육실 운영자에게 적용합니다.",
            "citations": [citation(law, "가상 교육실 운영자에게 적용합니다.")],
        }],
    }


def draft(*statements):
    return {"supported": True, "statements": list(statements)}


def run(documents, output, question="제공된 가상 자료의 내용을 설명해 주세요."):
    llm = FakeLLM(output)
    return generate_answer(question, documents, structured_llm=llm, as_of=AS_OF), llm


def assert_review(result, reason):
    assert result.needs_review is True
    # Caution-only sourced answers remain displayable; withheld answers hand off.
    assert result.handoff is (not bool(result.sources))
    assert reason in result.review_reasons
    assert result.review_message


def assert_rejected(result):
    assert result.sources == []
    assert result.needs_review is True
    assert result.handoff is True
    assert set(result.review_reasons) & {"invalid_evidence", "invalid_output"}


def test_normal_document_input_returns_exact_internal_contract(guide):
    result, llm = run([guide], draft(guide_statement(guide)))
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    serialized = json.loads(result.model_dump_json())
    assert set(serialized) == {"answer", "sources", "needs_review", "handoff"}
    assert type(serialized["handoff"]) is bool
    assert type(serialized["needs_review"]) is bool
    assert result.answer and "권고" in result.answer
    assert "교육실 안내에 한하여" in result.answer
    assert result.needs_review is False
    assert result.handoff is False
    assert result.review_reasons == []
    assert len(llm.messages) == 1
    assert result.sources[0].model_dump(exclude_none=True) == {
        key: value for key, value in guide.metadata.items() if key != "producer_note"
    }


def test_full_original_text_and_metadata_reach_model_without_mutation(guide):
    before = deepcopy(guide.model_dump())
    _, llm = run([guide], draft(guide_statement(guide)))
    messages = llm.messages[0]
    payload = json.loads(messages[1].content.split("\n", 1)[1])
    assert payload == [{"page_content": guide.page_content, "metadata": guide.metadata}]
    assert json.loads(messages[2].content.split("\n", 1)[1])["question"]
    assert guide.model_dump() == before


def test_law_duties_and_guidance_have_separate_labels(law, guide):
    result, _ = run([law, guide], draft(law_statement(law), guide_statement(guide)))
    assert "의무" in result.answer
    assert "권고" in result.answer
    assert "가상 교육실 운영자" in result.answer
    assert {source.chunk_id for source in result.sources} == {law.metadata["chunk_id"], guide.metadata["chunk_id"]}
    assert_review(result, "law_currentness_unverified")


def test_guide_cannot_be_promoted_to_legal_obligation(guide):
    statement = guide_statement(guide)
    statement["kind"] = "legal_obligation"
    result, _ = run([guide], draft(statement))
    assert_rejected(result)


def test_only_cited_documents_become_sources(guide, law):
    result, _ = run([guide, law], draft(guide_statement(guide)))
    assert [source.chunk_id for source in result.sources] == [guide.metadata["chunk_id"]]


def test_same_cited_document_is_serialized_once(guide):
    statement = guide_statement(guide)
    result, _ = run([guide], draft(statement, statement))
    assert len(result.sources) == 1


@pytest.mark.parametrize("documents", [[], [Document(page_content=" \n ", metadata={})]])
def test_no_usable_documents_do_not_call_model(documents):
    llm = FakeLLM(error=AssertionError("model must not be called"))
    result = generate_answer("자료가 있나요?", documents, structured_llm=llm, as_of=AS_OF)
    assert_review(result, "no_evidence")
    assert result.sources == []
    assert not llm.messages


@pytest.mark.parametrize("output", [
    {"supported": False, "statements": []},
    {"supported": True, "statements": []},
])
def test_model_abstention_is_no_evidence(guide, output):
    result, _ = run([guide], output)
    assert_review(result, "no_evidence")
    assert result.sources == []


@pytest.mark.parametrize("part,change", [
    ("claim", {"chunk_id": "invented-chunk"}),
    ("claim", {"quote": "원문에 없는 문장"}),
    ("claim", {"quote": " "}),
    ("condition", {"chunk_id": "invented-condition-chunk"}),
    ("condition", {"quote": "없는 적용 조건"}),
])
def test_wrong_source_or_quote_is_rejected(guide, part, change):
    statement = guide_statement(guide)
    target = statement["citations"][0] if part == "claim" else statement["conditions"][0]["citations"][0]
    target.update(change)
    result, _ = run([guide], draft(statement))
    assert_rejected(result)


@pytest.mark.parametrize("placement", ["draft", "statement", "citation"])
def test_llm_cannot_supply_source_metadata(guide, placement):
    output = draft(guide_statement(guide))
    forged_source = {"source_url": "https://invented.invalid/not-the-original"}
    if placement == "draft":
        output["sources"] = [forged_source]
    elif placement == "statement":
        output["statements"][0]["source_url"] = forged_source["source_url"]
    else:
        output["statements"][0]["citations"][0].update(forged_source)
    result, _ = run([guide], output)
    assert_rejected(result)


def test_old_law_requires_review_but_age_alone_does_not_mean_repealed(law):
    result, _ = run([law], draft(law_statement(law)))
    assert_review(result, "law_currentness_unverified")
    assert result.sources[0].effective_date == "2001-01-01"
    assert "폐지되었습니다" not in result.answer
    assert "효력이 없습니다" not in result.answer
    assert "현행 법령입니다" not in result.answer
    assert "검토" in result.answer or "확인" in result.answer


@pytest.mark.parametrize("value,reason", [
    (None, "effective_date_missing"),
    ("not-a-date", "effective_date_invalid"),
    ("2099-01-01", "effective_date_future"),
])
def test_missing_invalid_future_law_dates_are_not_assumed_current(law, value, reason):
    if value is None:
        law.metadata.pop("effective_date")
    else:
        law.metadata["effective_date"] = value
    result, _ = run([law], draft(law_statement(law)))
    assert_review(result, reason)
    assert "현행 법령입니다" not in result.answer


def test_recent_effective_date_does_not_prove_currentness(law):
    law.metadata["effective_date"] = AS_OF.isoformat()
    result, _ = run([law], draft(law_statement(law)))
    assert_review(result, "law_currentness_unverified")


def test_unknown_application_conditions_are_explicitly_deferred(guide):
    statement = guide_statement(guide)
    statement["conditions"] = []
    result, _ = run([guide], draft(statement))
    assert_review(result, "conditions_unverified")
    assert "적용 조건" in result.answer
    assert "보류" in result.answer or "확인" in result.answer


def test_condition_without_citation_is_rejected(guide):
    statement = guide_statement(guide)
    statement["conditions"][0]["citations"] = []
    result, _ = run([guide], draft(statement))
    assert_rejected(result)


def test_missing_metadata_requires_handoff_before_llm(guide):
    output = draft(guide_statement(guide))
    guide.metadata.pop("source_url")
    result, llm = run([guide], output)
    assert_review(result, "invalid_metadata")
    assert result.sources == []
    assert not llm.messages


def test_conflicting_chunk_ids_require_handoff_before_llm(guide):
    other = Document(page_content="다른 원문", metadata=deepcopy(guide.metadata))
    result, llm = run([guide, other], draft(guide_statement(guide)))
    assert_review(result, "invalid_metadata")
    assert result.sources == []
    assert not llm.messages


@pytest.mark.parametrize("error", [
    TimeoutError("secret timeout details"),
    httpx.ReadTimeout("secret timeout details"),
    APITimeoutError(request=httpx.Request("POST", "https://example.invalid")),
])
def test_timeout_is_distinct_from_missing_evidence(guide, error):
    llm = FakeLLM(error=error)
    result = generate_answer("가상 자료 설명", [guide], structured_llm=llm, as_of=AS_OF)
    assert_review(result, "llm_timeout")
    assert "no_evidence" not in result.review_reasons
    assert result.sources == []
    assert "secret" not in result.model_dump_json()


def test_provider_failure_has_sanitized_handoff(guide):
    result = generate_answer("가상 자료 설명", [guide], structured_llm=FakeLLM(error=RuntimeError("secret-api-key")), as_of=AS_OF)
    assert_review(result, "llm_error")
    assert "no_evidence" not in result.review_reasons
    assert "secret-api-key" not in result.model_dump_json()


@pytest.mark.parametrize("output", [None, "free text", {"supported": True}, {"supported": "true", "statements": []}])
def test_unstructured_output_is_not_used_as_answer(guide, output):
    result, _ = run([guide], output)
    assert_rejected(result)


def test_output_parser_error_is_invalid_output(guide):
    result = generate_answer("가상 자료 설명", [guide], structured_llm=FakeLLM(error=OutputParserException("private raw output")), as_of=AS_OF)
    assert_review(result, "invalid_output")
    assert "private raw output" not in result.model_dump_json()


def test_out_of_scope_has_no_llm_call_or_claimed_handoff_action(guide):
    llm = FakeLLM(error=AssertionError("must not call"))
    result = generate_answer("지금 불산이 누출됐는데 어떻게 중화해?", [guide], structured_llm=llm, as_of=AS_OF)
    assert_review(result, "emergency")
    assert "119" in result.answer and "기다리지" in result.answer
    assert not llm.messages
    assert result.sources == []
    assert "전달했습니다" not in result.review_message


@pytest.mark.parametrize("question", ["", " \n "])
def test_blank_question_is_caller_error(question):
    with pytest.raises(ValueError):
        generate_answer(question, [], structured_llm=FakeLLM())


def test_non_document_input_is_caller_error():
    with pytest.raises(TypeError):
        generate_answer("자료 설명", [{"page_content": "dict is not Document"}], structured_llm=FakeLLM())


@pytest.mark.parametrize("timeout_seconds", [30.0, 2.5])
def test_provider_factory_configures_timeout_and_disables_retries(guide, monkeypatch, timeout_seconds):
    observed = {}
    runnable = FakeLLM(draft(guide_statement(guide)))

    class Client:
        def with_structured_output(self, schema, **kwargs):
            observed["structured"] = kwargs
            return runnable

    def fake_chat_openai(**kwargs):
        observed["client"] = kwargs
        return Client()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", fake_chat_openai)
    result = generate_answer("가상 안내자료 설명", [guide], timeout_seconds=timeout_seconds, as_of=AS_OF)
    assert result.sources
    assert observed["client"]["timeout"] == timeout_seconds
    assert observed["client"]["max_retries"] == 0
    assert observed["structured"] == {"method": "json_schema", "strict": True}


def test_configuration_failure_is_a_distinct_handoff(guide, monkeypatch):
    def unavailable_client(**kwargs):
        raise ValueError("secret configuration payload")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", unavailable_client)
    result = generate_answer("가상 안내자료 설명", [guide], as_of=AS_OF)
    assert_review(result, "configuration_error")
    assert result.sources == []
    assert "secret" not in result.model_dump_json()


def test_no_documents_do_not_even_construct_provider(monkeypatch):
    def forbidden_client(**kwargs):
        raise AssertionError("provider should never be constructed")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", forbidden_client)
    result = generate_answer("근거가 있나요?", [], as_of=AS_OF)
    assert_review(result, "no_evidence")


def test_conflicting_effective_dates_require_version_review(law):
    newer = Document(page_content=law.page_content, metadata=deepcopy(law.metadata))
    newer.metadata["chunk_id"] = "fixture-law:999:newer"
    newer.metadata["effective_date"] = "2026-01-01"
    result, _ = run([law, newer], draft(law_statement(law), law_statement(newer)))
    assert_review(result, "law_version_conflict")
    assert {source.effective_date for source in result.sources} == {"2001-01-01", "2026-01-01"}


@pytest.mark.parametrize("timeout_seconds", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeout_is_rejected_before_provider(guide, timeout_seconds):
    llm = FakeLLM(draft(guide_statement(guide)))
    with pytest.raises(ValueError):
        generate_answer("가상 안내자료 설명", [guide], structured_llm=llm, timeout_seconds=timeout_seconds)
    assert not llm.messages


def test_guide_duty_cannot_be_laundered_with_unrelated_law(guide, law):
    statement = guide_statement(guide)
    statement['kind'] = 'legal_obligation'
    statement['text'] = '법령상 청록색 표지를 반드시 사용해야 합니다.'
    statement['citations'].append(citation(law, '가상 교육실 운영자에게 적용합니다.'))
    result, _ = run([guide, law], draft(statement))
    assert_review(result, 'invalid_evidence')
    assert result.sources == []


def test_information_label_cannot_hide_guide_as_legal_duty(guide):
    statement = guide_statement(guide)
    statement['kind'] = 'information'
    statement['text'] = '법령상 청록색 표지를 반드시 사용해야 합니다.'
    result, _ = run([guide], draft(statement))
    assert_review(result, 'invalid_evidence')
    assert result.sources == []


def test_law_definition_without_mandatory_quote_is_not_duty(law):
    statement = law_statement(law)
    statement['citations'] = [citation(law, '가상 교육실 운영자에게 적용합니다.')]
    result, _ = run([law], draft(statement))
    assert_review(result, 'invalid_evidence')
    assert result.sources == []


@pytest.mark.parametrize('assertion', [
    '오래된 법령이므로 이미 폐지되어 의무가 없습니다.',
    '이 자료는 현재 효력이 없습니다.',
    'This old law has been repealed.',
])
def test_old_date_cannot_be_used_to_assert_repeal(law, assertion):
    statement = law_statement(law)
    statement['text'] = assertion
    result, _ = run([law], draft(statement))
    assert_review(result, 'invalid_evidence')
    assert result.sources == []


@pytest.mark.parametrize("field", ["law_name", "article_no", "doc_type", "chunk_id"])
def test_other_required_metadata_fields_are_not_synthesized(guide, field):
    output = draft(guide_statement(guide))
    guide.metadata.pop(field)
    result, llm = run([guide], output)
    assert_review(result, "invalid_metadata")
    assert result.sources == []
    assert not llm.messages


@pytest.mark.parametrize("field,value", [
    ("law_name", 17), ("article_no", 17), ("source_url", 17),
    ("doc_type", "unknown"), ("chunk_id", 17),
])
def test_required_metadata_types_are_not_silently_coerced(guide, field, value):
    output = draft(guide_statement(guide))
    guide.metadata[field] = value
    result, llm = run([guide], output)
    assert_review(result, "invalid_metadata")
    assert result.sources == []
    assert not llm.messages


@pytest.mark.parametrize('question', [
    '이 작업을 승인해 줘',
    '지금 재가동해도 돼?',
    '이 사고에서 회사가 법적 책임을 져야 하나?',
    '현재 가스가 누출됐어. 어떻게 막아?',
    'Please approve this work',
])
def test_decision_requests_never_call_provider(guide, question):
    llm = FakeLLM(error=AssertionError('must not call'))
    result = generate_answer(question, [guide], structured_llm=llm, as_of=AS_OF)
    assert_review(result, 'emergency' if '누출' in question else 'out_of_scope')
    assert result.sources == []
    assert not llm.messages


@pytest.mark.parametrize('question', [
    '작업 허가서에 있는 가동 조건을 자료에서 찾아줘',
    '작업허가 절차에 따른 작업관리 항목을 알려줘',
])
def test_reference_lookup_is_not_a_safety_approval(guide, question):
    _, llm = run([guide], draft(guide_statement(guide)), question=question)
    assert len(llm.messages) == 1


def test_same_condition_on_consecutive_statements_is_written_once(guide):
    first, second = guide_statement(guide), guide_statement(guide)
    second["text"] = "제공된 안내자료는 표지 색을 청록색으로 하도록 권고합니다."
    result, _ = run([guide], draft(first, second))
    assert result.answer.count("교육실 안내에 한하여") == 1
    assert "적용 조건(위 2개 공통):" in result.answer
    lines = result.answer.splitlines()
    shared = next(i for i, line in enumerate(lines) if "위 2개 공통" in line)
    assert lines[shared - 1].startswith("- ") and lines[shared - 2].startswith("- ")
