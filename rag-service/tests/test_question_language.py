from rag.query import question_language


def test_question_script_decides_answer_language():
    assert question_language("What gloves should I wear for sulfuric acid?", "ko") == "en"
    assert question_language("Cần đeo găng tay gì khi dùng axit?", "ko") == "vi"
    assert question_language("硫酸应该怎么储存？", "ko") == "zh"
    assert question_language("តើត្រូវពាក់ស្រោមដៃអ្វី?", "en") == "km"
    assert question_language("황산 보관할 때 주의사항은?", "en") == "ko"


def test_mixed_or_short_questions_keep_screen_language():
    assert question_language("H2SO4 MSDS 8항 보호구 알려줘", "ko") == "ko"
    assert question_language("Can deo gang tay gi khi dung axit?", "vi") == "vi"   # 성조 없는 베트남어
    assert question_language("IPA?", "zh") == "zh"
