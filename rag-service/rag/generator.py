"""답변 생성 — 담당: 박진근

hits 만 근거로 답하고, sources · needs_review · handoff 를 채운다.
(지금은 틀이 동작하도록 넣은 임시 버전 — 규칙 다듬기는 생성 담당)
"""
import re
from typing import List

from rag.llm import call_llm
from rag.prompt import build_messages
from rag.schema import Hit, RagResponse, source_from_meta

NOT_FOUND = "제공된 자료에서 찾을 수 없습니다. 담당자에게 확인해 주세요."
DISCLAIMER = "\n\n※ 참고용 안내입니다. 현장 MSDS와 담당자 확인을 따르세요."

# 개별 판단을 요구하는 표현 — 근거가 있어도 담당자에게 넘긴다
HANDOFF_WORDS = ("우리 회사", "저희 회사", "책임이 있", "처벌받", "처벌 받", "소송", "괜찮을까", "고소")
# 수치가 들어간 답(농도·노출기준 등)은 담당자 확인 표시
NUMBER_PATTERN = re.compile(r"\d+(\.\d+)?\s*(%|ppm|mg|㎎|℃|°C|시간|분)")


def needs_review(hits: List[Hit], answer_text: str) -> bool:
    """근거 부족·수치(농도·노출기준) 포함 등 담당자 확인이 필요한가."""
    return not hits or bool(NUMBER_PATTERN.search(answer_text))


def needs_handoff(question: str, hits: List[Hit]) -> bool:
    """개별 법률 판단·사고 책임 질문이거나 근거가 없는가."""
    return not hits or any(w in question for w in HANDOFF_WORDS)


def generate(question: str, hits: List[Hit], language: str) -> RagResponse:
    """hits 가 비어 있으면 LLM 을 부르지 않고 "찾을 수 없음" + handoff.
    prompt.build_messages → llm.call_llm → schema.source_from_meta 로 sources 구성."""
    if not hits:
        return RagResponse(answer=NOT_FOUND, needs_review=True, handoff=True)

    answer_text = call_llm(build_messages(question, hits, language))

    sources, seen = [], set()
    for h in hits:
        src = source_from_meta(h["metadata"])
        key = (src.title, src.section)
        if key not in seen:
            seen.add(key)
            sources.append(src)

    return RagResponse(
        answer=answer_text + DISCLAIMER,
        sources=sources,
        needs_review=needs_review(hits, answer_text),
        handoff=needs_handoff(question, hits),
    )
