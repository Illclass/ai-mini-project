"""질문 다듬기 — 담당: 김규빈

문서가 한국어라서 검색 전에 질문을 한국어·표준 용어로 맞춘다.
"""
from functools import lru_cache
from typing import List

from rag.schema import TOPIC_LAW

# 동의어 — 질문에 왼쪽 표현이 있으면 오른쪽 표준 표현으로 바꾼 질문도 함께 검색한다 (원문 질문도 유지)
# 물질명: MSDS 의 물질명·다른 이름 (MSDS 13종 기준)
SYNONYMS = {
    "불산": "불화수소",
    "HF": "불화수소",
    "염산": "염화수소",
    "가성소다": "수산화나트륨",
    "양잿물": "수산화나트륨",
    "과수": "과산화수소",
    "암모니아": "암모니아수",
    "메틸알코올": "메탄올",
    "이소프로판올": "IPA",
    "이소프로필알코올": "IPA",
    "수산화테트라메틸암모늄": "TMAH",
    "현상액": "TMAH",
    "중대재해법": "중대재해 처벌 등에 관한 법률",
    "중대재해처벌법": "중대재해 처벌 등에 관한 법률",
    "중처법": "중대재해 처벌 등에 관한 법률",
}

# 법령 질문 전용 — 일상 표현 → 법령 용어 (화학 질문의 "노출기준" 등과 섞이지 않도록 법령 topic 에서만)
LAW_SYNONYMS = {
    "기준": "정의",
    "협력업체": "도급 용역 위탁",
    "협력사": "도급 용역 위탁",
    "하청": "도급 용역 위탁",
    "작업을 멈추": "작업중지",
    "대피": "작업중지",
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


# 번역해서 검색할 언어 — 한국어가 아니면 모두 번역한다.
# 처음에는 bge-m3 가 en · zh 를 번역 없이도 상위 5위 안에 찾아서 vi · km 만 번역했지만,
# 번역해야 한국어 동의어(기준→정의 등)가 적용된다. zh 6문항·en 6문항 모두 번역 후 1위 (질문당 약 +1초)
TRANSLATE_LANGUAGES = ("zh", "vi", "en", "km")


def to_korean(question: str, language: str) -> str:
    """한국어가 아닌 질문(TRANSLATE_LANGUAGES)을 한국어로 바꾼다. 번역에 실패하면 원문으로 검색한다."""
    if language not in TRANSLATE_LANGUAGES:
        return question
    try:
        return _translate(question) or question
    except Exception:
        return question


def expand_synonyms(question: str, topic: str = "") -> List[str]:
    """동의어를 반영한 검색용 질문 목록: 원문 + 단어별로 바꾼 질문 + 모두 바꾼 질문 (중복 없음)."""
    table = SYNONYMS | (LAW_SYNONYMS if topic == TOPIC_LAW else {})
    queries, combined = [question], question
    for word, standard in table.items():
        if word in question and standard not in question:
            queries.append(question.replace(word, standard))
            combined = combined.replace(word, standard)
    queries.append(combined)
    return list(dict.fromkeys(queries))


def normalize_question(question: str, language: str, topic: str = "") -> List[str]:
    """to_korean → expand_synonyms. retrieve() 에 넘길 검색용 질문 목록."""
    return expand_synonyms(to_korean(question.strip(), language), topic)
