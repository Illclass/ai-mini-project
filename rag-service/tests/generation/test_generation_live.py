"""Opt-in Generation-only real LLM tests; synthetic Documents, no retrieval."""
from datetime import date
import os

import pytest
from langchain_core.documents import Document

from rag.generator import generate_answer

pytestmark = [pytest.mark.live, pytest.mark.skipif(
    os.getenv("RAG_RUN_GENERATION_LIVE") != "1",
    reason="Set RAG_RUN_GENERATION_LIVE=1 for billable Generation LLM tests",
)]


@pytest.fixture(scope="module", autouse=True)
def live_key():
    from dotenv import load_dotenv
    if os.getenv("RAG_LIVE_ENV_FILE"):
        load_dotenv(os.environ["RAG_LIVE_ENV_FILE"])
    if not os.getenv("OPENAI_API_KEY"):
        pytest.fail("Generation LIVE requested but OPENAI_API_KEY is missing", pytrace=False)


def guide_document():
    return Document(
        page_content=("이 문서는 실제 안전지침이 아닌 가상 테스트 안내서입니다. "
                      "가상 알파 구역의 종이 기록철에는 청록색 표지를 사용할 것을 권장합니다. "
                      "이 권고의 적용 대상은 가상 알파 구역의 종이 기록철이며 전자 기록에는 적용하지 않습니다."),
        metadata={"law_name": "", "article_no": "", "source_url": "https://example.invalid/fictional-guide",
                  "doc_type": "guide", "chunk_id": "fictional-guide:1", "article_title": "가상 표지 권고"},
    )


def call(question, docs):
    result = generate_answer(question, docs, model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o"),
                             timeout_seconds=30, as_of=date(2026, 10, 22))
    operational = {"llm_timeout", "llm_error", "configuration_error", "invalid_output"}
    assert not operational.intersection(result.review_reasons), (
        "Generation LIVE failed: " + ",".join(result.review_reasons)
    )
    return result


def test_live_guide_answer_conditions_and_sources():
    doc = guide_document()
    result = call("가상 안내서가 권고하는 기록철 표지색과 적용 대상 및 예외를 설명해줘.", [doc])
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    assert "청록" in result.answer and "권고" in result.answer and "적용 조건" in result.answer
    assert "전자" in result.answer
    assert [s.chunk_id for s in result.sources] == [doc.metadata["chunk_id"]]
    assert result.sources[0].model_dump(exclude_none=True) == doc.metadata
    assert result.needs_review is False
    assert result.handoff is False


def test_live_old_law_and_guidance_are_distinguished():
    law = Document(
        page_content=("이 문서는 실제 법령이 아닌 가상 테스트 규정입니다. "
                      "가상 알파 구역에서 종이 기록철을 관리하는 담당자는 그 기록철을 17일 보관하여야 합니다. "
                      "적용 대상은 가상 알파 구역의 종이 기록철에 한정되며 전자 기록은 제외합니다."),
        metadata={"law_name": "가상테스트규정(실제 법령 아님)", "article_no": "제999조",
                  "source_url": "https://example.invalid/fictional-law", "doc_type": "law",
                  "chunk_id": "fictional-law:999:1", "effective_date": "2001-01-01", "paragraph": "제1항"},
    )
    result = call("가상 알파 구역 자료의 기록철 보관 의무 문구와 표지 권고를 구분하고 적용 대상과 예외를 설명해줘.",
                  [law, guide_document()])
    assert "17" in result.answer and "청록" in result.answer
    assert "법령 자료의 의무 문구" in result.answer and "권고 지침" in result.answer
    assert {s.chunk_id for s in result.sources} == {"fictional-law:999:1", "fictional-guide:1"}
    assert result.needs_review and result.handoff
    assert "law_currentness_unverified" in result.review_reasons
    assert next(s for s in result.sources if s.doc_type == "law").effective_date == "2001-01-01"
    assert "현재의 의무로 확정하지 않습니다" in result.answer


def test_live_missing_evidence_defers():
    result = call("이 자료에 없는 달의 평균 반지름을 알려주세요.", [guide_document()])
    assert result.sources == []
    assert result.needs_review and result.handoff
    assert result.review_reasons == ["no_evidence"]
