"""질문 다듬기 — 담당: 김규빈

문서가 한국어라서 검색 전에 질문을 한국어·표준 용어로 맞춘다.
"""
import re
from functools import lru_cache
from typing import List

from rag import lexicon
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
    "옮겨 담": "안전취급요령",     # MSDS 7항 표현 (없으면 14항 '운송'이 대신 걸림)
    "옮겨담": "안전취급요령",
    "소분": "안전취급요령",
    "이송": "안전취급요령",       # '이송'만 있으면 14항 '운송'이 먼저 걸린다
    "희석": "안전취급요령",
    "보호구": "노출방지 및 개인보호구",   # MSDS 8항 제목
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
def _translate(question: str, hints: tuple = ()) -> str:
    from rag.llm import call_llm  # 지연 import (테스트에서 LLM 을 부르지 않도록)
    # 질문에 나온 용어는 문서에 쓰인 한국어 용어로 옮기게 한다 (data/lexicon/glossary.json)
    system = TRANSLATE_PROMPT + ("\n용어 대응 (이 한국어 용어로 옮겨라): " + "; ".join(hints) if hints else "")
    return call_llm([{"role": "system", "content": system},
                     {"role": "user", "content": question}], timeout=15).strip()


# 번역해서 검색할 언어 — 한국어가 아니면 모두 번역한다.
# 처음에는 bge-m3 가 en · zh 를 번역 없이도 상위 5위 안에 찾아서 vi · km 만 번역했지만,
# 번역해야 한국어 동의어(기준→정의 등)가 적용된다. zh 6문항·en 6문항 모두 번역 후 1위 (질문당 약 +1초)
TRANSLATE_LANGUAGES = ("zh", "vi", "en", "km")


_VI_MARKS = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]")


def question_language(question: str, language: str) -> str:
    """질문 글자로 답변 언어를 정한다. 화면 언어가 한국어여도 영어로 물으면 영어로 답한다.
    한글·크메르·한자가 두 글자 이상이면 그 언어 (영문 물질명·MSDS 가 섞인 한국어 질문은 한국어),
    그런 글자 없이 로마자만 있으면 en·vi 화면은 그대로, 그 밖에는 베트남어 성조 표시가 있으면 vi, 없으면 en."""
    count = lambda pattern: len(re.findall(pattern, question))
    if count(r"[\u1780-\u17ff]") >= 2:
        return "km"
    if count(r"[\uac00-\ud7a3]") >= 2:
        return "ko"
    if count(r"[\u4e00-\u9fff]") >= 2:
        return "zh"
    if count(r"[A-Za-zÀ-ỹ]") >= 6 and len(re.findall(r"[A-Za-zÀ-ỹ]{2,}", question)) >= 2:
        if language in ("en", "vi"):
            return language
        return "vi" if _VI_MARKS.search(question) else "en"
    return language


def to_korean(question: str, language: str) -> str:
    """한국어가 아닌 질문(TRANSLATE_LANGUAGES)을 한국어로 바꾼다. 번역에 실패하면 원문으로 검색한다."""
    if language not in TRANSLATE_LANGUAGES:
        return question
    try:
        return _translate(question, lexicon.question_hints(question, language)) or question
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
