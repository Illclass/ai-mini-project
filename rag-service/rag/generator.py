"""답변 생성 — 담당: 박진근

hits 만 근거로 답하고, sources · needs_review · handoff 를 채운다.
"""
from typing import List

from rag.schema import Hit, RagResponse


def needs_review(hits: List[Hit], answer_text: str) -> bool:
    """근거 부족·수치(농도·노출기준) 포함 등 담당자 확인이 필요한가."""
    # TODO
    raise NotImplementedError


def needs_handoff(question: str, hits: List[Hit]) -> bool:
    """개별 법률 판단·사고 책임 질문이거나 근거가 없는가."""
    # TODO
    raise NotImplementedError


def generate(question: str, hits: List[Hit], language: str) -> RagResponse:
    """hits 가 비어 있으면 LLM 을 부르지 않고 "찾을 수 없음" + handoff.
    prompt.build_messages → llm.call_llm → schema.source_from_meta 로 sources 구성."""
    # TODO
    raise NotImplementedError
