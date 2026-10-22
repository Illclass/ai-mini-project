"""검색 → 생성 연결 — 담당: 김규빈 · 박진근 (공동)

API 가 부르는 유일한 함수는 answer(req) 하나다.
"""
from rag.schema import RagRequest, RagResponse


def is_emergency(question: str) -> bool:
    """노출·사고 상황 질문인가 ("눈에 들어갔어요", "흡입했어요" 등). True 면 비상 안내 우선 + handoff."""
    # TODO
    raise NotImplementedError


def answer(req: RagRequest) -> RagResponse:
    """흐름: is_emergency → query.normalize_question → retriever.retrieve → generator.generate → latency_ms."""
    # TODO
    raise NotImplementedError
