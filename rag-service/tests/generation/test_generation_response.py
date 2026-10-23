"""The agreed API shape is a separate conversion, not a router modification."""
from copy import deepcopy

import pytest

from rag.generator import GenerationOutput, SourceMetadata
from rag.generator import build_api_response


def output():
    return GenerationOutput(
        answer="가상 법령 자료의 의무 문구 [1] 및 권고 [2]",
        sources=[
            SourceMetadata(law_name="가상 규정", article_no="제2조", article_title="가상 정의",
                           source_url="https://example.invalid/law", doc_type="law",
                           chunk_id="law:2:1", effective_date="2001-01-01", paragraph="제2항"),
            SourceMetadata(law_name="", article_no="", article_title="가상 안내서",
                           source_url="https://example.invalid/guide", doc_type="guide",
                           chunk_id="guide:1"),
        ],
        needs_review=True, handoff=True,
    )


def test_api_shape_matches_agreement_without_mutating_internal_metadata():
    result = output()
    before = deepcopy(result.model_dump())
    result._review_reasons = ["law_currentness_unverified"]
    response = build_api_response(result, latency_ms=1250,
                                  doc_id_by_chunk_id={"law:2:1": "L2", "guide:1": "G1"})
    assert response.model_dump() == {
        "answer": result.answer,
        "sources": [
            {"doc_id": "L2", "section": "제2조 제2항", "title": "가상 규정", "url": "https://example.invalid/law"},
            {"doc_id": "G1", "section": "", "title": "가상 안내서", "url": "https://example.invalid/guide"},
        ],
        "needs_review": True, "handoff": True, "latency_ms": 1250,
    }
    assert result.model_dump() == before
    assert result.review_reasons == ["law_currentness_unverified"]


def test_same_doc_id_does_not_collapse_source_indices():
    result = output()
    result.sources[1] = result.sources[0].model_copy(update={"chunk_id": "law:2:2", "paragraph": "제3항"})
    response = build_api_response(result, latency_ms=0,
                                  doc_id_by_chunk_id={"law:2:1": "L2", "law:2:2": "L2"})
    assert len(response.sources) == 2
    assert response.answer == result.answer
    assert [source.doc_id for source in response.sources] == ["L2", "L2"]


def test_missing_mapping_never_invents_a_doc_id():
    with pytest.raises(ValueError, match="mapping is missing"):
        build_api_response(output(), latency_ms=1, doc_id_by_chunk_id={})


@pytest.mark.parametrize("value", ["", " ", None, 12, True])
def test_invalid_document_id_is_rejected(value):
    with pytest.raises(ValueError):
        build_api_response(output(), latency_ms=1,
                           doc_id_by_chunk_id={"law:2:1": value, "guide:1": "G1"})


@pytest.mark.parametrize("value", [-1, True, 1.5, float("inf"), float("nan"), "1250", None])
def test_invalid_latency_is_rejected(value):
    with pytest.raises(ValueError, match="latency_ms"):
        build_api_response(output(), latency_ms=value,
                           doc_id_by_chunk_id={"law:2:1": "L2", "guide:1": "G1"})


def test_no_evidence_preserves_review_flags_and_empty_sources():
    result = GenerationOutput(answer="판단 보류", sources=[], needs_review=True, handoff=True)
    response = build_api_response(result, latency_ms=0, doc_id_by_chunk_id={})
    assert response.sources == []
    assert response.needs_review and response.handoff


def test_missing_guide_title_is_not_invented():
    result = output()
    result.sources[1].article_title = None
    response = build_api_response(result, latency_ms=1,
                                  doc_id_by_chunk_id={"law:2:1": "L2", "guide:1": "G1"})
    assert response.sources[1].title == ""


@pytest.mark.parametrize("result,mapping", [(None, {}), (output(), [])])
def test_malformed_caller_types_are_rejected(result, mapping):
    with pytest.raises(TypeError):
        build_api_response(result, latency_ms=0, doc_id_by_chunk_id=mapping)


@pytest.mark.parametrize("article,paragraph,expected", [
    ("제2조", "제2호", "제2조 제2호"),
    ("제2조 제2항", "제2항", "제2조 제2항"),
    ("제2조제2항제1호", "제2항 제1호", "제2조제2항제1호"),
    ("제2조 제2항", "제2항 제1호", "제2조 제2항 제1호"),
    ("제2조제2항", "제2항제1호", "제2조제2항 제1호"),
    ("제2조", None, "제2조"),
    ("제2조", "", "제2조"),
])
def test_article_and_paragraph_preserve_section_detail(article, paragraph, expected):
    result = output()
    result.sources[0].article_no = article
    result.sources[0].paragraph = paragraph
    response = build_api_response(result, latency_ms=1,
                                  doc_id_by_chunk_id={"law:2:1": "L2", "guide:1": "G1"})
    assert response.sources[0].section == expected
