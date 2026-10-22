"""질문 다듬기 — 담당: 김규빈

문서가 한국어라서 검색 전에 질문을 한국어·표준 용어로 맞춘다.
"""
from typing import List

# 물질명 동의어 — 질문에 왼쪽 표현이 있으면 오른쪽 표준 이름으로 바꾼 질문도 함께 검색한다
SYNONYMS = {
    "불산": "불화수소",
    "HF": "불화수소",
    "IPA": "이소프로필알코올",
    "중대재해법": "중대재해 처벌 등에 관한 법률",
    "중대재해처벌법": "중대재해 처벌 등에 관한 법률",
    # TODO: 물질 목록이 정해지면 추가 (황산 H2SO4, 과산화수소 H2O2, TMAH ...)
}


def to_korean(question: str, language: str) -> str:
    """zh · vi 질문을 한국어로 바꾼다. ko 면 그대로."""
    if language == "ko":
        return question
    # TODO: zh · vi → ko 번역 (임시: 원문 그대로 검색)
    return question


def expand_synonyms(question: str) -> List[str]:
    """동의어를 반영한 검색용 질문 목록 (원문 포함, 중복 없음)."""
    queries = [question]
    for word, standard in SYNONYMS.items():
        if word in question and standard not in question:
            queries.append(question.replace(word, standard))
    return list(dict.fromkeys(queries))


def normalize_question(question: str, language: str) -> List[str]:
    """to_korean → expand_synonyms. retrieve() 에 넘길 검색용 질문 목록."""
    return expand_synonyms(to_korean(question.strip(), language))
