"""질문 다듬기 — 담당: 김규빈

문서가 한국어라서 검색 전에 질문을 한국어·표준 용어로 맞춘다.
"""
from typing import List

# 물질명 동의어 — 검색 전에 표준 이름으로 맞춘다 (예: "HF" → "불화수소")
SYNONYMS = {
    # TODO: "불산": "불화수소", "HF": "불화수소", "IPA": "이소프로필알코올", ...
}


def to_korean(question: str, language: str) -> str:
    """zh · vi 질문을 한국어로 바꾼다. ko 면 그대로."""
    # TODO
    raise NotImplementedError


def expand_synonyms(question: str) -> List[str]:
    """동의어를 반영한 검색용 질문 목록 (원문 포함)."""
    # TODO
    raise NotImplementedError


def normalize_question(question: str, language: str) -> List[str]:
    """to_korean → expand_synonyms. retrieve() 에 넘길 검색용 질문 목록."""
    # TODO
    raise NotImplementedError
