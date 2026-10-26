"""외국어 자료집 — 담당: 김규빈 (2026-10-26)

data/lexicon/ 의 두 파일을 읽는다. 표현을 고칠 때는 코드가 아니라 JSON 을 고친다.
- emergency.json: 외국어 비상 표현 ("TMAH沾到皮肤上了" 처럼 몸 부위 + 묻음·튐). rag/generator.py is_emergency 에 더해진다.
- glossary.json: 안전 용어 번역표. 질문 번역(rag/query.py)과 외국어 답변 생성(rag/prompt.py)에 번역어 힌트로만 쓴다.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

LEXICON_DIR = Path(__file__).resolve().parent.parent / "data" / "lexicon"
LANGUAGES = ("zh", "vi", "en", "km")
MAX_TERMS = 40   # 답변 생성에 넘기는 용어 수 상한 (토큰 절약)


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return json.loads((LEXICON_DIR / name).read_text(encoding="utf-8"))


def _fold(text: str, language: str) -> str:
    """비교용 글자: 베트남어는 성조를 빼고, 영어는 소문자, 한국어는 띄어쓰기를 지운다. 중국어·크메르어는 그대로."""
    if language == "vi":
        stripped = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
        return unicodedata.normalize("NFC", stripped).replace("đ", "d")
    if language == "en":
        return text.lower()
    if language == "ko":
        return re.sub(r"\s+", "", text)
    return text


def emergency_match(question: str) -> bool:
    """몸 부위와 묻음·튐 표현이 window 글자 안에 붙어 있거나 phrases 가 있으면 비상. 가정 표현이 있으면 이 규칙은 쓰지 않는다."""
    data = _load("emergency.json")
    window = data["window"]
    for language in (*LANGUAGES, "ko"):
        entry, text = data[language], _fold(question, language)
        if any(word in text for word in entry["hypothetical"]):
            continue
        if any(phrase in text for phrase in entry["phrases"]):
            return True
        for contact in entry["contact"]:
            for found in re.finditer(re.escape(contact), text):
                after = text[found.end():found.end() + window + 8]
                before = text[max(0, found.start() - window - 8):found.start()]
                for body in entry["body"]:
                    at = after.find(body)
                    if 0 <= at <= window:
                        return True
                    at = before.rfind(body)
                    if at >= 0 and len(before) - (at + len(body)) <= window:
                        return True
    return False


def _terms() -> list[dict]:
    return _load("glossary.json")["terms"]


def glossary_for(language: str, texts) -> dict:
    """검색된 원문에 실제로 나온 한국어 용어만 골라 {한국어: 번역어} 로 준다 (긴 용어부터, 최대 MAX_TERMS 개)."""
    if language not in LANGUAGES:
        return {}
    body = "\n".join(texts)
    found = [t for t in _terms() if t["ko"] in body and t.get(language)]
    found.sort(key=lambda t: -len(t["ko"]))
    return {t["ko"]: t[language] for t in found[:MAX_TERMS]}


def question_hints(question: str, language: str) -> tuple[str, ...]:
    """외국어 질문에 나온 용어의 한국어 문서 용어: ("hydrofluoric acid = 불산", ...). 질문 번역 힌트로 쓴다."""
    if language not in LANGUAGES:
        return ()
    text = _fold(question, language)
    return tuple(f"{t[language]} = {t['ko']}" for t in _terms()
                 if t.get(language) and _fold(t[language], language) in text)
