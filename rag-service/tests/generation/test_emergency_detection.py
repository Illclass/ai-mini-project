"""Generation-only incident regression tests; no retrieval, network or API key."""
from unittest.mock import Mock

import pytest
from langchain_core.documents import Document

from rag import generator
from rag.prompt import TEXT
from rag.schema import LANGUAGES


# Slack's category labels (e.g. [비상상황]) are deliberately omitted:
# users should not have to label their question for detection to work.
INCIDENTS = [
    "Developer 장비에서 TMAH가 작업복에 튀었습니다. 어떻게 해야 하나요?",
    "CVD 장비에서 가스 누출 경보가 발생했습니다. 현장 작업자는 어떻게 대응해야 하나요?",
    "설비에서 이상한 냄새가 나는데 어떤 가스인가요?",
    "Developer设备中的TMAH溅到工作服上了，我该怎么办？",
    "CVD设备的气体泄漏报警响了，现场工人该怎么办？",
    "设备有不明异味，是什么气体？",
    "TMAH từ máy Developer bắn vào quần áo bảo hộ của tôi. Tôi phải làm gì?",
    "Chuông cảnh báo rò rỉ khí ở máy CVD đang kêu. Tôi phải làm gì?",
    "Máy có mùi lạ, đó là khí gì?",
]


@pytest.mark.parametrize("question", INCIDENTS)
def test_incident_detected_without_category_label(question):
    assert generator.is_emergency(question)


@pytest.mark.parametrize("question", [
    "작업복에 약액이 묻었습니다.",
    "가스 누출 알람이 울리고 있습니다.",
    "설비에서 이상한 냄새가 납니다.",
    "TMAH ban vao quan ao bao ho cua toi.",
    "May co mui la, do la khi gi?",
    "我的工作服被TMAH溅到了。",
])
def test_incident_wording_variants(question):
    assert generator.is_emergency(question)


@pytest.mark.parametrize("question", [
    "Dry Etcher 챔버를 열어 내부 부품을 교체하려고 합니다. 어떤 유해물질을 확인해야 하나요?",
    "Wet Bench에서 불산 공급 용기를 교체할 예정입니다. 작업 전 어떤 사항을 확인해야 하나요?",
    "작업복 오염 예방 교육 자료를 설명해 주세요.",
    "누출 경보 점검 방법을 설명해 주세요.",
    "가스 누출 경보가 발생하지 않았습니다. 점검 주기는 무엇인가요?",
    "이상한 냄새가 나지 않습니다. 냄새 관련 교육 자료를 알려주세요.",
    "请介绍防止工作服污染的培训资料。",
    "气体报警器的检查周期是什么？",
    "设备没有异味，请介绍安全培训资料。",
    "Hãy giải thích cách phòng ngừa hóa chất bắn vào quần áo.",
    "Chu kỳ kiểm tra chuông cảnh báo khí là gì?",
    "Máy không có mùi lạ. Hãy giới thiệu tài liệu đào tạo.",
])
def test_learning_and_explicitly_absent_new_signals_are_not_incidents(question):
    # This tests the emergency guard only, not permission to perform a task.
    assert not generator.is_emergency(question)


@pytest.mark.parametrize("question", INCIDENTS)
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("entrypoint", ["documents", "team_hits"])
def test_incident_returns_notice_before_evidence_or_llm(monkeypatch, question, language, entrypoint):
    factory = Mock(side_effect=AssertionError("Must not create a provider"))
    monkeypatch.setattr(generator, "build_document_llm", factory)
    llm = Mock()
    llm.invoke.side_effect = AssertionError("Must not invoke a provider")
    # Deliberately invalid metadata proves emergency handling precedes evidence
    # validation and cannot accidentally return a generic evidence error.
    if entrypoint == "documents":
        result = generator.generate_answer(
            question, [Document(page_content="가상 테스트 자료", metadata={})],
            language=language, structured_llm=llm,
        )
        assert result.review_reasons == ["emergency"]
        expected_fields = {"answer", "sources", "needs_review", "handoff"}
    else:
        result = generator.generate(
            question, [{"text": "가상 테스트 자료", "metadata": {}}],
            language, structured_llm=llm,
        )
        expected_fields = {"answer", "sources", "needs_review", "handoff", "latency_ms"}
    assert result.answer == TEXT[language]["emergency"]
    assert result.needs_review is True and result.handoff is True
    assert result.sources == []
    assert set(result.model_dump()) == expected_fields
    factory.assert_not_called()
    llm.invoke.assert_not_called()
