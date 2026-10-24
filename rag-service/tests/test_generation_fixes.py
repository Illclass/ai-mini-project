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


def test_msds_data_tables_are_not_truncated_warnings():
    from rag.prompt import incomplete_critical_chunks

    def doc(no, text):
        return Document(page_content=text, metadata={"chunk_id": f"D9-s{no}", "doc_type": "msds", "msds_section_no": no})
    nfpa = "NFPA:\n 인화성\n 3\n 건강 불안정\n 2 0\n 특수 위험성"
    assert incomplete_critical_chunks([doc(16, nfpa), doc(9, "인화점 : 12 °C\n인화 하한값 : 자료없음 인화 하한값")]) == set()
    # 경고 문장이 있는 항목은 그대로 검사한다 (잘린 P 문구 → 잘림)
    assert incomplete_critical_chunks([doc(2, "P305 + P351 + P338 + P310 눈에 묻으면: 몇 분간 물로")]) == {"D9-s2"}


def test_law_item_list_gets_its_duty_sentence():
    text = ("제4조(사업주와 경영책임자등의 안전 및 보건 확보의무) ① 사업주 또는 경영책임자등은 종사자의 안전ㆍ보건상 유해 또는 위험을 방지하기 위하여\n"
            "그 사업 또는 사업장의 특성 및 규모 등을 고려하여 다음 각 호에 따른 조치를 하여야 한다.\n"
            "1. 재해예방에 필요한 인력 및 예산 등 안전보건관리체계의 구축 및 그 이행에 관한 조치\n2. 재해 발생 시 재발방지 대책의 수립 및 그 이행에 관한 조치")
    originals = {"L2-4": Document(page_content=text, metadata={"chunk_id": "L2-4"})}
    law = type("M", (), {"doc_type": "law"})()
    st = g.EvidenceStatement(kind="legal_obligation", text="안전보건관리체계 구축 조치가 열거되어 있습니다.",
                     citations=[g.Citation(chunk_id="L2-4", quote="1. 재해예방에 필요한 인력 및 예산 등 안전보건관리체계의 구축 및 그 이행에 관한 조치")], conditions=[])
    out = g._with_duty_chapeau(st, originals, {"L2-4": law})
    assert out.citations[0].quote.endswith("다음 각 호에 따른 조치를 하여야 한다.") and out.citations[0].quote in text
    assert g._supports_legal_duty(out.citations, {"L2-4": law})
    # 목록이 아닌 인용(벌칙 조항 등)은 손대지 않는다
    other = st.model_copy(update={"citations": [g.Citation(chunk_id="L2-4", quote="재해 발생 시 재발방지 대책의 수립")]})
    assert g._with_duty_chapeau(other, originals, {"L2-4": law}) is other


def test_kosha_numbered_item_counts_as_source_requirement():
    guide = type("M", (), {"doc_type": "guide"})()
    md = {"K8-8_2": guide}
    item = g.Citation(chunk_id="K8-8_2", quote="(5) 개인보호구(내산성 보호복 등)를 철저하게 착용한다.")
    must = g.Citation(chunk_id="K8-8_2", quote="불산을 다룰 때는 보호안경까지 착용을 해야 사고로 인한 피해를 막을 수 있다.")
    plain = g.Citation(chunk_id="K8-8_2", quote="이 지침은 불산 취급 사업장에 적용한다.")   # 번호 없는 설명 문장
    assert g._source_technical_requirement(item, md) and g._source_technical_requirement(must, md)
    assert not g._source_technical_requirement(plain, md)
