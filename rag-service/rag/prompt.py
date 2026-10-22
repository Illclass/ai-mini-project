"""프롬프트 — 담당: 박진근

규칙(기획서): 검색된 근거만 사용, 없으면 "찾을 수 없음", 개별 법률 판단·책임 단정 금지,
답변 언어 = 요청 language, 끝에 "참고용, 현장 MSDS·담당자 확인" 문구.
"""
from typing import Dict, List

from rag.schema import Hit

SYSTEM_PROMPT = ""  # TODO


def build_messages(question: str, hits: List[Hit], language: str) -> List[Dict[str, str]]:
    """LLM 에 보낼 messages ([{"role": ..., "content": ...}])."""
    # TODO
    raise NotImplementedError
