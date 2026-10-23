"""Closed LLM 호출 — 담당: 박진근

모델·키는 환경변수(LLM_MODEL, OPENAI_API_KEY)에서 읽는다.
"""
import os
import math
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


class RAGConfigurationError(RuntimeError):
    """Missing or incompatible generation configuration."""


def validate_timeout(timeout_seconds: float) -> float:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("timeout_seconds must be a finite positive number")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a finite positive number")
    return float(timeout_seconds)


def build_structured_llm(output_schema, model: str = DEFAULT_MODEL, *, timeout_seconds: float = 30.0):
    """구조화 생성 호출. SDK 네트워크 timeout 적용, 자동 재시도 없음.

    output_schema는 생성 담당 generator가 전달한다. 이 모듈은 검색·출처 검증을
    하지 않으며 generator를 import하지 않는다. 전체 요청의 절대 시간 제한은 아니다.
    """
    from langchain_openai import ChatOpenAI
    timeout = validate_timeout(timeout_seconds)
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model cannot be blank")
    try:
        client = ChatOpenAI(model=model, temperature=0, timeout=timeout, max_retries=0)
        return client.with_structured_output(output_schema, method="json_schema", strict=True)
    except Exception as exc:
        raise RAGConfigurationError("OpenAI generation configuration is missing or invalid") from exc
