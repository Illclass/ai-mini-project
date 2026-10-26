"""Closed LLM 호출 — 담당: 박진근

모델·키는 환경변수(LLM_MODEL, OPENAI_API_KEY)에서 읽는다.
"""
import os
import math
from typing import Dict, List

from openai import OpenAI

from rag.schema import ENV_LLM_MODEL

DEFAULT_MODEL = "gpt-6-luna"   # 팀 결정: Luna 사용 (gpt-4o 보다 답변률↑, 비용 약 1/20)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(max_retries=2)
    return _client


def _sampling_options(model: str, temperature: float) -> dict:
    """Luna는 추론을 끄고 기존 비추론 호출의 sampling 설정을 유지한다.

    GPT-6 Luna 기본 추론 설정에서는 temperature를 보낼 수 없다.
    다른 모델의 호출 설정과 환경변수의 기본 모델은 바꾸지 않는다.
    """
    options = {"temperature": temperature}
    if model == "gpt-6-luna":
        options["reasoning_effort"] = "none"
    return options


def call_llm(messages: List[Dict[str, str]], timeout: float = 30.0) -> str:
    """LLM 응답 본문. 타임아웃·재시도 포함, 실패하면 예외(→ API 에서 503)."""
    model = os.getenv(ENV_LLM_MODEL, DEFAULT_MODEL)
    resp = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        **_sampling_options(model, 0.2),
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
        client = ChatOpenAI(model=model, timeout=timeout, max_retries=0,
                            **_sampling_options(model, 0))
        return client.with_structured_output(output_schema, method="json_schema", strict=True)
    except Exception as exc:
        raise RAGConfigurationError("OpenAI generation configuration is missing or invalid") from exc
