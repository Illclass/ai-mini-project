"""Synthetic fixtures only. Not real MSDS, legal advice or workplace instructions."""
from copy import deepcopy
from langchain_core.documents import Document
from rag.prompt import critical_passages

PRODUCT_ID = "demo-DEMO-001"
PRODUCT_LINES = {
    "product_name": ("TrainingLiquid-A", "제품명: TrainingLiquid-A"),
    "product_number": ("DEMO-001", "제품번호: DEMO-001"),
    "concentration": ("1.0%", "농도: 1.0%"),
    "revision_date": ("2026-01-01", "개정일: 2026-01-01"),
}


def synthetic_msds():
    return Document(page_content=(
        "가상 테스트 MSDS입니다.\n"
        + "\n".join(line for _, line in PRODUCT_LINES.values())
        + "\n경고: 이 자료를 실제 현장 작업에 사용하지 마세요.\n"
        "적용 대상은 가상 교육실 2곳입니다. 실제 작업장은 제외합니다."
    ), metadata={
        "doc_id": "FIXTURE-D1", "doc_type": "msds", "topic": "chemical_safety",
        "title": "TrainingLiquid-A 가상 테스트 MSDS", "section": "1. 가상 제품 정보",
        "source_url": "https://example.invalid/fictional-msds",
        "chunk_id": "FIXTURE-D1-s1", "effective_date": "2026-01-01",
        "product_id": PRODUCT_ID, "substance": "가상 학습액", "cas_no": "",
        "supplier": "가상 공급자", "msds_section_no": 1,
    })


TRANSLATIONS = {
    "ko": ["경고: 이 자료를 실제 현장 작업에 사용하지 마세요.", "적용 대상은 가상 교육실 2곳입니다.", "실제 작업장은 제외합니다."],
    "zh": ["警告：不要将此资料用于真实现场作业。", "适用对象为2个虚拟培训室。", "实际工作场所不适用。"],
    "vi": ["Cảnh báo: Không sử dụng tài liệu này cho công việc thực tế tại hiện trường.", "Phạm vi áp dụng là 2 phòng đào tạo giả định.", "Không áp dụng cho nơi làm việc thực tế."],
}


def synthetic_draft(doc, language="ko"):
    cid = doc.metadata["chunk_id"]
    descriptions = {"ko": "TrainingLiquid-A는 이 가상 자료의 제품명입니다.",
                    "zh": "这份虚拟资料中的产品名称是TrainingLiquid-A。",
                    "vi": "Tên sản phẩm trong tài liệu giả định này là TrainingLiquid-A."}
    conditions = {"ko": "가상 교육실 2곳에 한정됩니다.", "zh": "仅限2个虚拟培训室。",
                  "vi": "Chỉ áp dụng cho 2 phòng đào tạo giả định."}
    passages = critical_passages([doc])
    return {
        "supported": True,
        "statements": [{"kind": "information", "text": descriptions[language],
                        "citations": [{"chunk_id": cid, "quote": "제품명: TrainingLiquid-A"}],
                        "conditions": [{"text": conditions[language], "citations": [
                            {"chunk_id": cid, "quote": "적용 대상은 가상 교육실 2곳입니다."}]}]}],
        "critical_translations": [{"passage_id": pid, "text": text}
                                  for pid, text in zip(passages, TRANSLATIONS[language], strict=True)],
        "product_facts": [{"field": key, "value": value,
                           "citations": [{"chunk_id": cid, "quote": quote}]}
                          for key, (value, quote) in PRODUCT_LINES.items()],
    }


class StubLLM:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return deepcopy(self.result)


def hit(doc):
    return {"text": doc.page_content, "score": 0.0, "metadata": deepcopy(doc.metadata)}
