"""Closed LLM 호출 — 담당: 박진근

모델·키는 환경변수(LLM_MODEL, OPENAI_API_KEY)에서 읽는다.
"""
from typing import Dict, List


def call_llm(messages: List[Dict[str, str]], timeout: float = 30.0) -> str:
    """LLM 응답 본문. 타임아웃·재시도 포함, 실패하면 예외(→ API 에서 503)."""
    # TODO
    raise NotImplementedError
