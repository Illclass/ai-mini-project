"""질문 다듬기 — 담당: 김규빈

문서가 한국어라서 검색 전에 질문을 한국어·표준 용어로 맞춘다.
"""
from functools import lru_cache
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


TRANSLATE_PROMPT = (
    "다음 질문을 한국어로 번역하라. 반도체 공장의 화학물질 안전·산업안전 법령 문서를 검색하는 데 쓴다. "
    "화학물질명은 한국어 표준 이름(예: 불화수소, 황산, 수산화테트라메틸암모늄)으로, 장비명·약어(TMAH, IPA, CVD)는 그대로 둔다. "
    "번역문만 출력하고 답하거나 설명하지 마라."
)


@lru_cache(maxsize=512)
def _translate(question: str) -> str:
    from rag.llm import call_llm  # 지연 import (테스트에서 LLM 을 부르지 않도록)
    return call_llm([{"role": "system", "content": TRANSLATE_PROMPT},
                     {"role": "user", "content": question}], timeout=15).strip()


# 번역해서 검색할 언어. bge-m3 는 en · zh 질문을 번역 없이도 잘 찾아서(hit@5 100%) vi · km 만 번역한다.
# (번역 없이 vi · km 은 67% → 번역 후 100%, eval/results/20261023_1139_retrieval.md)
TRANSLATE_LANGUAGES = ("vi", "km")


def to_korean(question: str, language: str) -> str:
    """vi · km 질문을 한국어로 바꾼다. 그 밖의 언어는 그대로 검색한다. 번역에 실패하면 원문으로 검색한다."""
    if language not in TRANSLATE_LANGUAGES:
        return question
    try:
        return _translate(question) or question
    except Exception:
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
