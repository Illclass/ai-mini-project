"""답변 보류 오탐 수정 테스트 — 담당: 김규빈. 인덱스·LLM 없이 돈다.

- 인용 비교: PDF 줄바꿈(단어 중간 포함)만 무시, 숫자 경계는 유지
- 제품 식별 4항목을 MSDS 원문에서 서버가 직접 추출
- 번역 문자 검사: 금액 단위(억원)·괄호 속 한국어 용어 병기만 허용
"""
from langchain_core.documents import Document

from rag import generator as g
from rag.prompt import translation_valid


def test_same_text_ignores_pdf_line_breaks_inside_words():
    source = "기한을 직접 정하거나 추정하\n지 않는다."
    assert g._same_text("기한을 직접 정하거나 추정하지 않는다.", source)
    assert not g._same_text("기한을 직접 정한다.", source)


def test_same_text_keeps_number_boundaries():
    assert not g._same_text("100", "10 0")
    assert g._same_text("10 0", "10\n0")


def _msds(cid, no, text):
    return Document(page_content=text, metadata={"chunk_id": cid, "doc_type": "msds", "product_id": "sigma-179124",
                                                 "cas_no": "67-64-1", "msds_section_no": no})


DOCS = [
    _msds("D9-s1", 1, "가. 제품명 :\n Acetone\n제품 번호 : 179124\n상표 : SIGALD"),
    _msds("D9-s3", 3, "화학물질명 CAS 번호 또는 함유량 (% w/w)\n식별번호\nAcetone 67-64-1 >= 95 - <= 100"),
    _msds("D9-s16", 16, "최종 개정일자 : 2026.07.14"),
]


def test_source_product_facts_reads_sections_1_3_16():
    facts = {f.field: f for f in g._source_product_facts(DOCS)}
    assert {k: f.value for k, f in facts.items()} == {
        "product_name": "Acetone", "product_number": "179124",
        "concentration": ">= 95 - <= 100", "revision_date": "2026.07.14"}
    for f in facts.values():   # 인용은 원문 그대로
        src = next(d for d in DOCS if d.metadata["chunk_id"] == f.citations[0].chunk_id)
        assert f.citations[0].quote in src.page_content


def test_source_product_facts_needs_all_four_and_one_product():
    assert g._source_product_facts(DOCS[:2]) == []                      # 개정일 없음
    other = Document(page_content="제품 번호 : 339741", metadata={**DOCS[0].metadata, "product_id": "sigma-339741"})
    assert g._source_product_facts(DOCS + [other]) == []               # 제품 두 개


def test_translation_allows_won_amount_and_korean_gloss_only():
    assert translation_valid("", "pháp luật quy định phạt tối đa 10억원", "vi")
    assert translation_valid("", "tai nạn lao động nghiêm trọng (중대산업재해) là", "vi")
    assert not translation_valid("", "tai nạn lao động 중대산업재해 là", "vi")   # 괄호 없는 한글은 여전히 거부
    assert not translation_valid("", "Phải đeo găng tay. 보호구를 착용하세요", "vi")
