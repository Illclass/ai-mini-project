"""Equipment/task prompt integration with fictional documents and scripted LLMs.

These tests check prompt delivery and server validation, not real LLM judgement.
"""
from copy import deepcopy
import json

import pytest
from langchain_core.documents import Document

from rag.generator import generate_answer
from rag.prompt import TEXT
from rag.schema import LANGUAGES
from chembridge_fixtures import StubLLM


@pytest.fixture
def equipment_guide():
    return Document(
        page_content=(
            "실제 설비나 작업 절차가 아닌 가상 테스트 자료입니다.\n"
            "DEMO-E1 안내표의 색상은 청록색입니다.\n"
            "적용 대상은 가상 교육 화면입니다."
        ),
        metadata={
            "doc_id": "DEMO-EQUIPMENT", "doc_type": "guide",
            "law_name": "", "article_no": "", "chunk_id": "DEMO-EQUIPMENT:1",
            "source_url": "https://example.invalid/fictional-equipment",
            "title": "가상 교육 장비 안내표", "section": "안내표",
        },
    )


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("mode", ["qa", "learn", "precheck"])
def test_task_prompt_reaches_model_and_unsupported_draft_uses_existing_fallback(equipment_guide, language, mode):
    question = "Dry Etcher 챔버를 열어 내부 부품을 교체하려고 합니다. 어떤 유해물질을 확인해야 하나요?"
    before = deepcopy(equipment_guide.model_dump())
    llm = StubLLM({"supported": False, "statements": []})
    result = generate_answer(question, [equipment_guide], language=language, mode=mode, structured_llm=llm)

    assert len(llm.calls) == 1
    messages = llm.calls[0]
    system = messages[0].content
    # Check the new rules reach the active provider path in every existing mode.
    # The fake LLM does NOT interpret these instructions or prove it obeys them.
    assert "장비·작업 질문의 근거 범위:" in system
    assert "작업 전 질문에 답하는 방법:" in system
    assert f"답변 언어: {language}. mode: {mode}." in system
    assert question not in system
    assert json.loads(messages[1].content.split("\n", 1)[1]) == [
        {"page_content": before["page_content"], "metadata": before["metadata"]}
    ]
    assert json.loads(messages[2].content.split("\n", 1)[1]) == {"question": question}
    assert equipment_guide.model_dump() == before
    assert result.answer == TEXT[language]["no_evidence"]
    assert result.sources == [] and result.needs_review and result.handoff
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}


@pytest.mark.parametrize("forged_sop", [False, True])
def test_precheck_preserves_real_source_and_rejects_fabricated_sop_quote(equipment_guide, forged_sop):
    cid = equipment_guide.metadata["chunk_id"]
    quote = "DEMO-E1 안내표의 색상은 청록색입니다."
    condition = "적용 대상은 가상 교육 화면입니다."
    draft = {
        "supported": True,
        "statements": [{
            "kind": "information", "text": quote,
            "citations": [{"chunk_id": cid, "quote": "가상 SOP에 이 안내표의 색상이 지정되어 있습니다." if forged_sop else quote}],
            "conditions": [{"text": condition, "citations": [{"chunk_id": cid, "quote": condition}]}],
        }],
    }
    result = generate_answer(
        "DEMO-E1 안내표 자료에서 확인할 내용을 설명해 주세요.",
        [equipment_guide], mode="precheck", structured_llm=StubLLM(draft),
    )
    assert result.needs_review
    assert result.handoff is forged_sop
    if forged_sop:
        assert result.review_reasons == ["invalid_evidence"]
        assert result.sources == [] and quote not in result.answer
    else:
        assert quote in result.answer and condition in result.answer
        assert TEXT["ko"]["precheck"] in result.answer
        assert result.review_reasons == ["precheck_requires_review"]
        for field, value in equipment_guide.metadata.items():
            assert result.sources[0].model_dump()[field] == value


@pytest.mark.parametrize("question,reason", [
    ("Dry Etcher 챔버를 열어 내부 부품을 교체하려고 합니다. 어떤 유해물질을 확인해야 하나요?", "no_evidence"),
    ("Wet Bench에서 불산 공급 용기를 교체할 예정입니다. 작업 전 어떤 사항을 확인해야 하나요?", "product_unverified"),
])
def test_missing_equipment_or_product_evidence_never_calls_llm(question, reason):
    llm = StubLLM(error=AssertionError("No evidence must not call the provider"))
    result = generate_answer(question, [], structured_llm=llm)
    assert not llm.calls
    assert result.review_reasons == [reason]
    assert result.sources == [] and result.needs_review and result.handoff
