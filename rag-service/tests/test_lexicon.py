"""외국어 자료집 (data/lexicon) — 비상 표현 사전과 안전 용어집."""
import json
import re
from pathlib import Path

import pytest

from rag import lexicon
from rag.generator import is_emergency

EMERGENCY = [
    "TMAH沾到皮肤上了，该怎么办？",
    "硫酸溅到眼睛里了",
    "氢氟酸沾到手上了",
    "Axit dính vào da tôi rồi, phải làm sao?",
    "Hóa chất bắn vào mắt tôi",
    "Acid got on my hands, what should I do?",
    "Some TMAH splashed into my eyes",
    "I swallowed some cleaning solution",
    "អាស៊ីតប្រឡាក់ស្បែកខ្ញុំ",
]
GENERAL = [
    "如果沾到皮肤应该怎么处理？",
    "化学品沾到皮肤时如何急救？",
    "Nếu hóa chất dính vào da thì phải làm gì?",
    "What should I do if acid gets on my skin?",
    "What PPE do I need when using methanol?",
    "使用甲醇时需要佩戴哪些防护用品？",
    "Khi dùng metanol cần đeo đồ bảo hộ nào?",
    "ប្រសិនបើអាស៊ីតប្រឡាក់ស្បែក តើត្រូវធ្វើអ្វី?",
]


@pytest.mark.parametrize("question", EMERGENCY)
def test_lexicon_catches_body_contact(question):
    assert is_emergency(question)


@pytest.mark.parametrize("question", GENERAL)
def test_lexicon_ignores_hypothetical_and_general(question):
    assert not lexicon.emergency_match(question)


def test_suggested_questions_do_not_become_emergencies():
    """화면 추천 질문(frontend locales)이 사전 때문에 새로 비상으로 바뀌지 않는다."""
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    texts = []
    paths = [*root.glob("locales/*.js"), *(root / "api" / n for n in ("recommendations.js", "suggestions.js", "candidates.json"))]
    for path in paths:
        if path.exists():
            texts += re.findall(r"['\"]([^'\"\n]{8,200})['\"]", path.read_text(encoding="utf-8"))
    assert len(texts) > 200   # 파일이 옮겨져 빈 목록을 검사하는 일이 없도록
    flagged = [t for t in texts if lexicon.emergency_match(t.replace("{context}", "TMAH"))]
    assert flagged == []


def test_glossary_is_complete_and_unique():
    terms = json.loads((lexicon.LEXICON_DIR / "glossary.json").read_text(encoding="utf-8"))["terms"]
    assert len({t["ko"] for t in terms}) == len(terms)
    for t in terms:
        assert all(t.get(lang, "").strip() for lang in ("ko", *lexicon.LANGUAGES)), t["ko"]
        assert not re.search(r"[가-힣]", " ".join(t[lang] for lang in lexicon.LANGUAGES)), t["ko"]


def test_glossary_only_terms_in_retrieved_text():
    terms = lexicon.glossary_for("zh", ["8. 노출방지 및 개인보호구\n보안경 착용, 보호장갑: 침투 시간 480 분"])
    assert terms["보안경"] == "安全眼镜" and terms["침투 시간"] == "穿透时间"
    assert "중대산업재해" not in terms
    assert lexicon.glossary_for("ko", ["보안경"]) == {}


def test_question_hints_map_foreign_terms_to_korean():
    hints = lexicon.question_hints("What PPE is needed for hydrofluoric acid?", "en")
    assert "hydrofluoric acid = 불산" in hints
    assert "axit sunfuric = 황산" in lexicon.question_hints("Nên bảo quản axit sunfuric như thế nào?", "vi")
