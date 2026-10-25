"""B 승인 범위의 적재/평가 회귀. 가상 원문과 명시적 대역만 사용한다."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from langchain_core.documents import Document

from eval import run_eval
from ingest import ingest_msds
from rag import chain, generator, retriever
from rag.schema import TOPIC_LAW, RagResponse


def test_long_msds_sections_round_trip_without_splitting_conditions():
    text = "\n".join(
        f"{n}. 항목 {n}\n" + (
            "보호구 재질 표: 공급자에게 확인하십시오.\n" * 100
            + "다른 물질과 혼합할 경우 공급자에게 연락하십시오."
            if n == 8 else "해당 항목의 원문입니다. 표와 설명을 보존합니다. " * 8
        ) for n in range(1, 17)
    )
    sections = ingest_msds.split_sections(text)
    chunks = ingest_msds.build_chunks(text, "SYNTH", "demo-product", "가상물질",
                                      "가상공급자", "", "2026-01-01",
                                      "https://example.invalid/msds")
    assert len(sections) == len(chunks) == 16
    for section, chunk in zip(sections, chunks):
        assert chunk["page_content"].split("\n", 1)[1] == section["body"]
        assert chunk["metadata"]["chunk_id"] == f'SYNTH-s{section["no"]}'
        assert chunk["metadata"]["product_id"] == "demo-product"
        assert chunk["metadata"]["effective_date"] == "2026-01-01"
        assert chunk["metadata"]["source_url"] == "https://example.invalid/msds"
    long_chunk = chunks[7]
    assert len(long_chunk["page_content"]) > 1200
    hit = {"text": long_chunk["page_content"], "metadata": long_chunk["metadata"], "score": 0.0}
    before = deepcopy(hit)
    assert retriever.drop_truncated([hit]) == [hit]
    assert hit == before


@pytest.mark.parametrize("reason,category", [
    ("retrieval_empty", "retrieval_empty"), ("no_evidence", "insufficient_evidence"),
    ("invalid_evidence", "validation_failure"), ("claim_mismatch", "validation_failure"),
    ("invalid_translation", "validation_failure"), ("invalid_metadata", "validation_failure"),
    ("incomplete_warning_context", "validation_failure"),
    ("invalid_output", "parse_error"), ("verification_unavailable", "verifier_error"),
    ("llm_timeout", "llm_timeout"), ("llm_error", "provider_error"),
    ("configuration_error", "configuration_error"), ("request_error", "request_error"),
    ("emergency", "review_required"), ("product_unverified", "review_required"),
    ("future_unknown_reason", "unclassified"),
])
def test_failure_categories_do_not_become_false_not_found_success(reason, category):
    response = {"sources": [], "handoff": True, "review_reasons": [reason]}
    assert run_eval.classify_outcome(response) == category
    assert run_eval.judge_behavior(response, "not_found") is (
        category in {"retrieval_empty", "insufficient_evidence"})
    assert run_eval.judge_behavior(response, "handoff") is (category == "review_required")
    assert not run_eval.judge_behavior(response, "answer")


def test_system_error_takes_priority_over_absence_and_caution():
    response = {"sources": [], "handoff": True,
                "review_reasons": ["no_evidence", "retrieval_empty", "emergency", "invalid_output"]}
    assert run_eval.classify_outcome(response) == "parse_error"
    assert not run_eval.judge_behavior(response, "not_found")
    assert not run_eval.judge_behavior(response, "handoff")


def test_valid_answer_caution_and_unclassified_deferral_are_distinct():
    response = {"sources": [{"doc_id": "SYNTH"}], "handoff": False, "needs_review": True,
                "review_reasons": ["conditions_unverified", "law_currentness_unverified"]}
    assert run_eval.judge_behavior(response, "answer")
    assert not run_eval.judge_behavior(response, "handoff")
    assert not run_eval.judge_behavior(response, "typo")
    assert run_eval.classify_outcome({"sources": [], "handoff": True}) == "unclassified"


def test_run_full_continues_and_reports_error_totals_without_raw_exceptions(monkeypatch, capsys):
    error = generator.GenerationUnavailable("DO_NOT_EXPOSE")
    error.reason = "llm_timeout"
    def response(reason):
        r = generator.GenerationAPIResponse(answer="가상 응답", sources=[], needs_review=True,
                                             handoff=True, latency_ms=0)
        r._review_reasons = [reason]
        return r
    # preflight loses its private reasons in chain; evaluator recovers them locally.
    early = generator.preflight_result("지금 누출 사고가 났어요", "ko")
    assert early is not None and "emergency" in early.review_reasons
    provider = Mock(side_effect=[error, RuntimeError("DO_NOT_EXPOSE"), response("invalid_output"),
                                response("verification_unavailable"), response("retrieval_empty"),
                                RagResponse(**early.model_dump())])
    monkeypatch.setattr(chain, "answer", provider)
    questions = [{"id": f"Q{i}", "question": "가상 자료의 내용은?", "topic": TOPIC_LAW,
                  "language": "ko", "expected_behavior": "not_found"} for i in range(6)]
    questions[-1].update(question="지금 누출 사고가 났어요", expected_behavior="handoff")
    run_eval.run_full(questions)
    text = capsys.readouterr().out
    assert provider.call_count == 6
    assert "DO_NOT_EXPOSE" not in text and "지금 누출" not in text
    assert "동작 정확도: 2/6" in text
    for category in ("llm_timeout", "request_error", "parse_error", "verifier_error",
                     "retrieval_empty", "review_required"):
        assert f"{category}=1" in text


def test_real_chain_private_reason_reaches_evaluator_without_public_api_change(monkeypatch):
    # No generation-scope supported-verifier autouse fixture applies to this file.
    # Malformed output fails before any semantic verifier call.
    d = Document(page_content="가상 안내서는 청록색입니다.", metadata={
        "doc_id": "SYNTH-GUIDE", "doc_type": "guide", "chunk_id": "SYNTH-GUIDE-1",
        "law_name": "", "article_no": "", "title": "가상 안내서", "section": "표지",
        "source_url": "https://example.invalid/guide"})
    monkeypatch.setattr(chain, "retrieve", lambda *a, **k: [
        {"text": d.page_content, "metadata": d.metadata, "score": 0.0}])
    provider = Mock(); provider.invoke.return_value = {"supported": True, "statements": "malformed"}
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: provider)
    verifier = Mock(side_effect=AssertionError("Verifier must not run for malformed output"))
    monkeypatch.setattr(generator, "build_verification_llm", verifier)
    from rag.schema import RagRequest
    result = chain.answer(RagRequest(question="가상 안내서의 내용은?", topic=TOPIC_LAW))
    payload = {**result.model_dump(), "review_reasons": result.review_reasons}
    assert run_eval.classify_outcome(payload) == "parse_error"
    assert not run_eval.judge_behavior(payload, "not_found")
    assert set(result.model_dump()) == set(RagResponse.model_fields)
    assert "review_reasons" not in result.model_dump_json()
    verifier.assert_not_called()
