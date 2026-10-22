"""Closed LLM 호출 — 담당: 박진근

모델·키는 환경변수(LLM_MODEL, OPENAI_API_KEY)에서 읽는다.
"""
import os
from typing import Dict, List

from openai import OpenAI

from rag.schema import ENV_LLM_MODEL

DEFAULT_MODEL = "gpt-4o"

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(max_retries=2)
    return _client


def call_llm(messages: List[Dict[str, str]], timeout: float = 30.0) -> str:
    """LLM 응답 본문. 타임아웃·재시도 포함, 실패하면 예외(→ API 에서 503)."""
    resp = _get_client().chat.completions.create(
        model=os.getenv(ENV_LLM_MODEL, DEFAULT_MODEL),
        messages=messages,
        temperature=0.2,
        timeout=timeout,
    )
    return (resp.choices[0].message.content or "").strip()
