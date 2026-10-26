"""답변 보류 오탐 수정 테스트 — 담당: 김규빈. 인덱스·LLM 없이 돈다.

- 인용 비교: PDF 줄바꿈(단어 중간 포함)만 무시, 숫자 경계는 유지
- 제품 식별 4항목을 MSDS 원문에서 서버가 직접 추출
- 번역 문자 검사: 금액 단위(억원)·괄호 속 한국어 용어 병기만 허용
- 응급 감지: 몸에 묻음·튐·삼킴을 과거형으로 말하면 응급
"""
import pytest
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


def test_generate_retries_once_only_for_verification_failures(monkeypatch):
    def result(reason, ok=False):
        r = g.GenerationOutput(answer="ok" if ok else "보류", sources=[], needs_review=not ok, handoff=not ok)
        r._review_reasons = [reason]
        return r
    hits = [{"text": "원문", "score": 0.1, "metadata": {"chunk_id": "K1-1", "doc_id": "K1"}}]
    for first, expected_calls in [("claim_mismatch", 2), ("no_evidence", 1), ("verification_unavailable", 1)]:
        calls = []
        monkeypatch.setattr(g, "generate_answer", lambda *a, **k: calls.append(1) or result(first))
        monkeypatch.setattr(g, "build_api_response", lambda r, **k: g.RagResponse(answer=r.answer, sources=[], needs_review=True, handoff=True, latency_ms=0))
        if first == "verification_unavailable":
            with pytest.raises(g.GenerationUnavailable) as error:
                g.generate("보호구는?", hits, "ko")
            assert error.value.reason == first
        else:
            g.generate("보호구는?", hits, "ko")
        assert len(calls) == expected_calls, first


def _pipeline_document():
    return Document(page_content="공급라인 상태를 확인한다.", metadata={
        "doc_id": "TEST", "doc_type": "guide", "chunk_id": "TEST-1", "title": "테스트 자료",
        "section": "작업 전 확인", "source_url": "https://example.invalid/pipeline",
    })


def test_pipeline_reports_recommendation_failure_at_its_check(monkeypatch, caplog):
    import linecache

    monkeypatch.setattr(g._PIPELINE_LOG, "propagate", True)
    doc = _pipeline_document()
    draft = {"supported": True, "statements": [{
        "kind": "recommendation", "text": "공급라인 상태를 반드시 확인해야 합니다.",
        "citations": [{"chunk_id": "TEST-1", "quote": doc.page_content}], "conditions": [],
    }]}
    provider = type("Provider", (), {"invoke": lambda self, messages: draft})()
    monkeypatch.setattr(g, "build_verification_llm", lambda *a, **k: pytest.fail("local failure must stop verifier"))
    with caplog.at_level("INFO", logger="chembridge.pipeline"):
        result = g.generate_answer("공급라인 점검 자료", [doc], structured_llm=provider)
    assert result.review_reasons == ["invalid_evidence"]
    records = [record for record in caplog.records if getattr(record, "pipeline_event", {}).get("check") == "recommendation_force"]
    assert len(records) == 1
    record = records[0]
    assert record.funcName == "generate_answer"
    assert 'check="recommendation_force"' in linecache.getline(record.pathname, record.lineno)
    assert record.pipeline_event["reason"] == "invalid_evidence"
    assert record.pipeline_event["status"] == "held"
    assert all(record.getMessage() == "pipeline_stage" for record in caplog.records)
    assert doc.page_content not in str([record.pipeline_event for record in caplog.records])


def test_pipeline_measures_provider_and_local_validation_separately(monkeypatch, caplog):
    monkeypatch.setattr(g._PIPELINE_LOG, "propagate", True)
    doc = _pipeline_document()
    clock = [100.0]
    monkeypatch.setattr(g, "perf_counter", lambda: clock[0])

    class Provider:
        def invoke(self, messages):
            clock[0] += 5.0
            return {"supported": True, "statements": [{
                "kind": "information", "text": doc.page_content,
                "citations": [{"chunk_id": "TEST-1", "quote": doc.page_content}], "conditions": [],
            }]}

    class Verifier:
        def invoke(self, messages):
            clock[0] += 7.0
            return {"assessments": [{"claim_id": "s0", "verdict": "supported"}]}

    monkeypatch.setattr(g, "build_verification_llm", lambda *a, **k: Verifier())
    hits = [{"text": doc.page_content, "score": 0.1, "metadata": doc.metadata}]
    with caplog.at_level("INFO", logger="chembridge.pipeline"):
        result = g.generate("공급라인 점검 자료", hits, "ko", structured_llm=Provider())
    events = {record.pipeline_event["stage"]: record.pipeline_event for record in caplog.records}
    assert result.sources and not result.handoff
    assert events["generation_draft"]["duration_ms"] == 5000.0
    assert events["evidence_validation"]["duration_ms"] == 0.0
    assert events["semantic_verification"]["duration_ms"] == 7000.0
    assert events["generation_attempt"]["duration_ms"] == 12000.0
    assert events["response_mapping"]["status"] == "ok"
    assert events["generation_attempt"]["attempt"] == 1


@pytest.mark.parametrize("reason", ["llm_timeout", "llm_error", "configuration_error", "verification_unavailable", "invalid_output"])
def test_generate_raises_typed_unavailability_for_operational_failures(monkeypatch, reason):
    result = g.GenerationOutput(answer="보류", sources=[], needs_review=True, handoff=True)
    result._review_reasons = [reason]
    monkeypatch.setattr(g, "generate_answer", lambda *a, **k: result)
    with pytest.raises(g.GenerationUnavailable) as error:
        g.generate("자료 확인", [], "ko")
    assert error.value.reason == reason
    assert str(error.value) == "Generation provider is temporarily unavailable"


def test_document_and_clause_numbers_may_come_from_chunk_header():
    doc = Document(page_content="[KOSHA K-1-2023 유해화학물질 저장 관련 지침 7.2 응급조치]\n7.2 응급조치\n응급조치를 취하여야 한다.",
                   metadata={"chunk_id": "K1-7_2"})
    cit = [g.Citation(chunk_id="K1-7_2", quote="응급조치를 취하여야 한다.")]
    heads = g._cited_headers(cit, {"K1-7_2": doc})
    assert g._quantities_supported("K-1-2023 지침의 7.2항에 응급조치가 있습니다.", cit, source_headers=heads)
    assert not g._quantities_supported("K-1-2023 지침은 16개 항목입니다.", cit, source_headers=heads)   # 머리글에 없는 숫자
    assert not g._quantities_supported("2023 % 농도", cit, source_headers=heads)                       # 수치·단위는 머리글로 통과 안 됨


def test_only_cited_or_hazard_warnings_are_attached():
    msds = lambda no: type("M", (), {"doc_type": "msds", "msds_section_no": no})()
    md = {"D1-s2": msds(2), "D1-s6": msds(6)}
    assert g._is_hazard_statement(("D1-s2", "H314 피부에 심한 화상과 눈에 손상을 일으킴"), md)
    assert not g._is_hazard_statement(("D1-s2", "P280 보호장갑을 착용하시오."), md)      # 예방조치 문구는 인용될 때만
    assert not g._is_hazard_statement(("D1-s6", "H314 피부에 심한 화상"), md)              # 2항이 아니면 아님


@pytest.mark.parametrize("question", [
    "황산이 묻고 마셨는데 어떻게 해", "황산이 손에 묻었어요", "황산을 마셨어요", "눈에 황산이 들어갔어",
    "불산이 손에 닿았어요", "硫酸溅到手上了", "I drank some sulfuric acid", "Axit ban vao tay toi",
])
def test_body_contact_and_swallowing_are_emergencies(question):
    from rag.generator import is_emergency
    assert is_emergency(question)


@pytest.mark.parametrize("question", [
    "황산 피부 접촉 시 조치는?", "희석할 때 손에 묻지 않게 하려면?", "황산을 옮겨 담을 때 보호구는?", "물 마시는 곳은 어디 두나요?",
])
def test_contact_prevention_questions_are_not_emergencies(question):
    from rag.generator import is_emergency
    assert not is_emergency(question)


@pytest.mark.parametrize("text", [
    "이 자료에는 보안경을 확인하는 구체적인 기준이 나오지 않아요.",
    "보안경에 대해서는 이 자료들에서 화학물질별 확인 방법을 찾을 수 없어요.",
    "The materials do not specify eye protection.",
])
def test_absence_statements_are_detected(text):
    # 자료에 없다는 문장은 인용으로 뒷받침할 수 없어 검증 AI 가 거부한다 → 빼고 고정 안내를 붙인다
    assert g._is_absence_statement(text)


@pytest.mark.parametrize("text", [
    "이 MSDS에는 발암성 자료가 없다고 적혀 있어요.",   # 원문 '자료없음'을 옮긴 문장은 남긴다
    "장갑은 제조업체에 확인을 받아 선정하세요.",
    "자료에 따라 보호구를 착용하세요.",
])
def test_source_content_is_not_treated_as_absence(text):
    assert not g._is_absence_statement(text)


@pytest.mark.parametrize("question, expected", [
    ("ពេលផ្ទុក សារធាតុគីមី តើមានការប្រុងប្រយ័ត្នអ្វីចំពោះ ការលេចធ្លាយ និងការបំពុល?", False),   # 누출 관련 주의사항은? (추천 질문)
    ("សារធាតុគីមីកំពុងលេចធ្លាយ តើខ្ញុំត្រូវធ្វើអ្វី?", True),                                      # 약품이 새고 있어요
    ("ឧស្ម័នបានលេចធ្លាយ", True),                                                                  # 가스가 샜어요
])
def test_khmer_leak_noun_is_not_an_emergency(question, expected):
    from rag.generator import is_emergency
    assert is_emergency(question) is expected


def test_kosha_page_furniture_split_by_text_is_ignored_in_guide_translation():
    # 쪽번호와 머리글 사이에 본문 조각이 낀 실제 K-1-2023 배치
    original = ("(9) 화학물질이 새어 나가는 경우에 반응 및 혼합 등에 따른 화재\n\n- 2 -\n\n폭발을 일\n\n\n"
                "KOSHA Guide K-1-2023\n\n으키거나 독성이 강한 유해가스 나 증기가 발생할 우려가 있는 물질은 별도\n장소에 저장한다.")
    translated = "(9) If a chemical could cause a fire or explosion when it leaks, store it in a separate location."
    from rag.prompt import translation_valid
    assert translation_valid(original, translated, "en", source_doc_type="guide")
    assert not translation_valid(original, translated.replace("(9)", "(8)"), "en", source_doc_type="guide")


def test_dropped_list_marker_is_restored_from_source():
    item = g.CriticalTranslation(passage_id="p1", text="Không được sử dụng vật chứa có nguy cơ bị vỡ hoặc rò rỉ.")
    fixed = g._with_source_list_marker(item, "(3) 운반 도중 파손되거나 누설 위험이 있는 용기를 사용해서는 아니 된다.")
    assert fixed.text.startswith("(3) ")
    assert g._with_source_list_marker(fixed, "(3) 원문").text.count("(3)") == 1   # 이미 있으면 그대로
    assert g._with_source_list_marker(item, "운반 도중 파손 위험").text == item.text  # 번호 없는 원문은 그대로


def test_ingest_title_line_and_numbered_heading_are_not_part_of_warning():
    from rag.prompt import critical_passages
    body = ("[S1 가상 현장 안전지침 (DEMO-A, 시연용) 13.3 약액이 누출되었을 때]\n13.3 약액이 누출되었을 때\n"
            "누출 지점에서 벗어나고 주변 사람을 대피시킨다.")
    doc = Document(page_content=body, metadata={"chunk_id": "S1-13_3", "doc_type": "guide", "title": "S1 가상 현장 안전지침 (DEMO-A, 시연용)"})
    quotes = [q for _, q in critical_passages([doc]).values()]
    assert all(not q.startswith("[") and "13.3" not in q for q in quotes)


def test_translation_amounts_ordinals_and_avoid_match_source():
    from rag.prompt import translation_valid
    law = "경영책임자등은 1년 이상의 징역 또는 10억원 이하의 벌금에 처한다."
    assert translation_valid(law, "punished by imprisonment for at least 1 year or a fine of up to 1 billion won.", "en")
    assert translation_valid(law, "bị phạt tù từ 1 năm trở lên hoặc phạt tiền không quá 1 tỷ won.", "vi")
    assert not translation_valid(law, "imprisonment for at least 1 year or a fine of up to 100 million won.", "en")
    third = "제3자에게 도급한 경우에는 제2항의 조치를 하여야 한다."
    assert translation_valid(third, "If work is contracted to a third party, it must take the measures in paragraph ②.", "en")
    assert not translation_valid(third, "If work is contracted to a second party, it must take the measures in paragraph ②.", "en")
    assert translation_valid("P273 환경으로 배출하지 마시오.", "P273 Avoid release to the environment.", "en")


def test_quantity_check_reads_article_numbers_and_hcodes():
    from rag.generator import _quantities_supported
    from rag.generator import Citation
    law = [Citation(chunk_id="L1", quote="제44조의2(화학사고 발생 시설에 대한 가동중지명령) ① 같은 조 제2항")]
    assert _quantities_supported("Article 44-2 ① under paragraph 2", law)
    msds = [Citation(chunk_id="M1", quote="유해·위험 문구 : H318 눈에 심한 손상을 일으킴.")]
    assert _quantities_supported("Câu cảnh báo nguy hại: H318 Gây tổn thương mắt nghiêm trọng.", msds)
    temp = [Citation(chunk_id="M2", quote="20 °C 이하에서 보관")]
    assert not _quantities_supported("Store below -20 °C.", temp)
    assert not _quantities_supported("Store below 25 °C.", temp)


def test_example_parenthesis_period_does_not_split_warning():
    from langchain_core.documents import Document
    from rag.prompt import critical_passages
    raw = "내부 압력이 빠져나올 수 있도록(예. 초과압 밸브) 용기를 밀폐할 것\n가연성 물질 근처에 보관하지 마십시오."
    doc = Document(page_content=raw, metadata={"chunk_id": "M1", "doc_type": "msds", "msds_section_no": 7})
    quotes = [q for _, q in critical_passages([doc]).values()]
    assert any("(예. 초과압 밸브) 용기를 밀폐할 것" in q for q in quotes)
