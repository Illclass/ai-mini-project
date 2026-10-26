"""Opt-in billable calls. Synthetic MSDS and permitted real text are separate cases."""
from datetime import date
import json
import os
from pathlib import Path

import pytest
from langchain_core.documents import Document

from rag.generator import generate_answer, build_document_llm
from chembridge_fixtures import PRODUCT_ID, synthetic_msds

pytestmark = [pytest.mark.live, pytest.mark.skipif(
    os.getenv("RAG_RUN_GENERATION_LIVE") != "1", reason="Explicit opt-in required for real LLM calls")]


@pytest.fixture(scope="module", autouse=True)
def live_key():
    from dotenv import load_dotenv
    if os.getenv("RAG_LIVE_ENV_FILE"): load_dotenv(os.environ["RAG_LIVE_ENV_FILE"])
    if not os.getenv("OPENAI_API_KEY"):
        pytest.fail("LIVE requested without OPENAI_API_KEY", pytrace=False)


def record(name, language, result):
    if os.getenv("RAG_GENERATION_EVAL_OUTPUT"):
        with open(os.environ["RAG_GENERATION_EVAL_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"fixture": name, "language": language,
                                     "result": result.model_dump(exclude_none=True),
                                     "review_reasons": result.review_reasons}, ensure_ascii=False) + "\n")


class RecordingLLM:
    """Opt-in synthetic/public evaluation diagnostics; never used by the API."""
    def __init__(self, name, language):
        self.name, self.language = name, language
        self.llm = build_document_llm(os.getenv("LLM_MODEL", "gpt-4o"))

    def invoke(self, messages):
        raw = self.llm.invoke(messages)
        if os.getenv("RAG_GENERATION_EVAL_OUTPUT"):
            with open(os.environ["RAG_GENERATION_EVAL_OUTPUT"] + ".drafts", "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"fixture": self.name, "language": self.language,
                                         "draft": raw.model_dump()}, ensure_ascii=False) + "\n")
        return raw


@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_live_synthetic_msds_learning_keeps_warnings(language):
    doc = synthetic_msds()
    question = {"ko": "처음 배우는 사람에게 이 가상 제품 자료의 제품명, 적용 대상과 경고를 쉽게 설명해줘.",
                "zh": "请向新员工简单说明这份虚拟产品资料的产品名称、适用范围和警告。",
                "vi": "Hãy giải thích dễ hiểu cho nhân viên mới về tên sản phẩm, phạm vi áp dụng và cảnh báo trong tài liệu giả định này."}[language]
    result = generate_answer(question, [doc], language=language, mode="learn", product_id=PRODUCT_ID,
                             structured_llm=RecordingLLM("synthetic_msds", language),
                             as_of=date(2026, 10, 22), timeout_seconds=30)
    record("synthetic_msds", language, result)
    assert [source.chunk_id for source in result.sources] == [doc.metadata["chunk_id"]], result.review_reasons
    assert "TrainingLiquid-A" in result.answer
    assert "실제 현장 작업에 사용하지 마세요" in result.answer
    assert result.needs_review and result.handoff
    assert "msds_applicability_unverified" in result.review_reasons


@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_live_permitted_public_regulation_excerpt_not_korean_current_law(language):
    fixture = json.loads((Path(__file__).parent / "fixtures/permitted_osha_excerpt.json").read_text())
    doc = Document(**fixture["document"])
    question = {"ko": "제공된 미국 조문 발췌에 적힌 MSDS 보관 의무 문구와 장소 조건만 설명해줘. 한국 적용 여부는 판단하지 마.",
                "zh": "只说明所提供美国条文摘录中的MSDS保存义务和地点条件，不判断其是否适用于韩国。",
                "vi": "Chỉ giải thích nghĩa vụ lưu giữ MSDS và điều kiện địa điểm trong trích đoạn quy định Hoa Kỳ được cung cấp. Không kết luận áp dụng tại Hàn Quốc."}[language]
    result = generate_answer(question, [doc], language=language, topic="serious_accident_law",
                             structured_llm=RecordingLLM("permitted_us_regulation_excerpt", language),
                             as_of=date(2026, 10, 22), timeout_seconds=30)
    record("permitted_us_regulation_excerpt", language, result)
    assert [source.chunk_id for source in result.sources] == [doc.metadata["chunk_id"]], result.review_reasons
    assert result.sources[0].source_url == doc.metadata["source_url"]
    assert "law_currentness_unverified" in result.review_reasons
    assert "effective_date_missing" in result.review_reasons
    assert result.needs_review and result.handoff
