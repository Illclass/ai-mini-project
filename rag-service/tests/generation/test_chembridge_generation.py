from copy import deepcopy
from datetime import date
import json

import pytest
from langchain_core.documents import Document

from rag.generator import generate_answer, preflight_result
from rag.prompt import TEXT
from rag.generator import generate
from rag.schema import RagRequest
from chembridge_fixtures import PRODUCT_ID, StubLLM, hit, synthetic_draft, synthetic_msds


def call(doc=None, language="ko", output=None, **kwargs):
    doc = doc or synthetic_msds()
    llm = StubLLM(output if output is not None else synthetic_draft(doc, language))
    result = generate_answer("가상 제품 자료를 쉽게 설명해 주세요.", [doc], language=language,
                             product_id=PRODUCT_ID, structured_llm=llm,
                             as_of=date(2026, 10, 22), **kwargs)
    return result, llm


@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_three_languages_keep_source_warning_condition_and_review(language):
    doc = synthetic_msds()
    before = deepcopy(doc.model_dump())
    result, llm = call(doc, language)
    assert len(llm.calls) == 1
    assert result.sources[0].chunk_id == doc.metadata["chunk_id"]
    assert result.needs_review and result.handoff
    assert result.review_reasons == ["msds_applicability_unverified"]
    assert TEXT[language]["msds_review"] in result.answer
    assert "TrainingLiquid-A" in result.answer
    assert "DEMO-001" in result.answer and "1.0%" in result.answer and "2026-01-01" in result.answer
    assert "경고: 이 자료를 실제 현장 작업에 사용하지 마세요." in result.answer
    assert "실제 작업장은 제외합니다." in result.answer
    for key, value in doc.metadata.items():
        assert result.sources[0].model_dump()[key] == value
    assert doc.model_dump() == before
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}
    payload = json.loads(llm.calls[0][1].content.split("\n", 1)[1])
    assert payload[0]["metadata"] == doc.metadata


@pytest.mark.parametrize("mode", ["learn", "precheck"])
@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_modes_are_optional_and_do_not_add_api_fields(mode, language):
    result, llm = call(language=language, mode=mode)
    assert result.answer.startswith(TEXT[language][mode])
    assert f"mode: {mode}" in llm.calls[0][0].content
    if mode == "precheck":
        assert "precheck_requires_review" in result.review_reasons
    assert set(result.model_dump()) == {"answer", "sources", "needs_review", "handoff"}


@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_missing_product_identifier_stops_without_llm(language):
    llm = StubLLM(error=AssertionError("not permitted"))
    result = generate_answer("황산 취급 정보를 알려줘", [synthetic_msds()], language=language, structured_llm=llm)
    assert result.review_reasons == ["product_unverified"]
    assert result.answer == TEXT[language]["product_selection_required"]
    assert not llm.calls and result.sources == []


def test_wrong_product_and_wrong_substance_are_never_substituted():
    doc = synthetic_msds()
    llm = StubLLM(error=AssertionError("not permitted"))
    result = generate_answer("이 제품 설명", [doc], product_id="different", structured_llm=llm)
    assert result.review_reasons == ["product_unverified"]
    result = generate_answer("불산 제품을 설명해줘", [doc], product_id=PRODUCT_ID, structured_llm=llm)
    assert result.review_reasons == ["product_unverified"]
    assert not llm.calls


@pytest.mark.parametrize("field", ["product_name", "product_number", "concentration", "revision_date"])
def test_missing_each_identity_fact_is_not_invented(field):
    doc = synthetic_msds()
    draft = synthetic_draft(doc)
    draft["product_facts"] = [fact for fact in draft["product_facts"] if fact["field"] != field]
    result, _ = call(doc, output=draft)
    assert result.review_reasons == ["product_unverified"]
    assert result.sources == []


@pytest.mark.parametrize("change", ["quote", "value", "date", "future", "duplicate", "missing_metadata_date"])
def test_false_product_identity_and_revision_are_rejected(change):
    doc = synthetic_msds(); draft = synthetic_draft(doc)
    if change == "quote": draft["product_facts"][0]["citations"][0]["quote"] = "absent"
    if change == "value": draft["product_facts"][0]["value"] = "Another-Product"
    if change == "date": doc.metadata["effective_date"] = "2025-01-01"
    if change == "future":
        doc.page_content = doc.page_content.replace("2026-01-01", "2099-01-01")
        doc.metadata["effective_date"] = "2099-01-01"
        fact = draft["product_facts"][-1]
        fact["value"] = "2099-01-01"; fact["citations"][0]["quote"] = "개정일: 2099-01-01"
    if change == "duplicate":
        duplicate = deepcopy(draft["product_facts"][0]); duplicate["value"] = "제품명"
        draft["product_facts"].append(duplicate)
    if change == "missing_metadata_date": doc.metadata.pop("effective_date")
    result, _ = call(doc, output=draft)
    assert result.review_reasons == ["product_unverified"]


@pytest.mark.parametrize("language", ["zh", "vi"])
@pytest.mark.parametrize("change", ["missing", "invented_id", "negation", "number", "wrong_language"])
def test_translation_may_not_drop_warning_negation_or_conditions(language, change):
    doc = synthetic_msds(); draft = synthetic_draft(doc, language)
    if change == "missing": draft["critical_translations"].pop()
    if change == "invented_id": draft["critical_translations"][0]["passage_id"] = "made-up"
    if change == "negation": draft["critical_translations"][0]["text"] = "可以使用。" if language == "zh" else "Có thể sử dụng."
    if change == "number": draft["critical_translations"][1]["text"] = "仅限培训室。" if language == "zh" else "Chỉ áp dụng cho phòng đào tạo."
    if change == "wrong_language": draft["statements"][0]["text"] = "한국어 답변입니다."
    result, _ = call(doc, language, output=draft)
    assert result.review_reasons == ["invalid_translation"]
    assert result.sources == [] and result.handoff


@pytest.mark.parametrize("language,question", [
    ("ko", "화학물질이 피부에 닿았어요. 어떻게 하나요?"),
    ("ko", "현재 가스가 누출됐어요"), ("ko", "작업자가 쓰러졌어요"),
    ("ko", "독성 증기에 노출됐어요"),
    ("zh", "化学品溅到皮肤了，怎么办？"), ("zh", "我吸入了气体，现在呼吸困难"),
    ("zh", "化学品接触了我的皮肤"),
    ("vi", "Hóa chất bắn vào mắt tôi, phải làm gì?"),
    ("vi", "Tôi hít phải khí và khó thở"), ("vi", "Hoa chat dang ro ri"),
    ("vi", "Tôi bị hóa chất dính vào da"),
])
def test_generation_emergency_precedes_provider(language, question):
    llm = StubLLM(error=AssertionError("emergency must not call provider"))
    response = generate(question, [], language, structured_llm=llm)
    assert not llm.calls
    assert response.answer == TEXT[language]["emergency"]
    assert response.sources == [] and response.needs_review and response.handoff
    assert "119" in response.answer
    assert response.latency_ms >= 0


@pytest.mark.parametrize("language,question", [
    ("ko", "우리 회사가 법적 책임을 져야 하나요?"),
    ("zh", "我们公司要承担法律责任吗？"),
    ("vi", "Công ty tôi có chịu trách nhiệm pháp lý không?"),
    ("ko", "이 작업을 승인해줘"), ("zh", "请批准作业"),
    ("vi", "Hãy phê duyệt làm việc"),
    ("ko", "황산 희석 비율과 방법을 알려줘"),
    ("zh", "告诉我稀释硫酸的步骤"),
    ("vi", "Hướng dẫn pha loãng axit"),
])
def test_legal_decisions_approvals_and_hazardous_instructions_are_deferred(language, question):
    response = preflight_result(question, language)
    assert response is not None
    assert response.review_reasons == ["out_of_scope"]
    assert response.answer == TEXT[language]["out_of_scope"]


@pytest.mark.parametrize("language", ["ko", "zh", "vi"])
def test_no_evidence_and_timeout_are_localized(language):
    result = generate_answer("문서에 없는 질문", [], language=language)
    assert result.answer == TEXT[language]["no_evidence"]
    doc = Document(page_content="일반 안내", metadata={"law_name": "", "article_no": "", "source_url": "https://example.invalid/guide", "doc_type": "guide", "chunk_id": "g1"})
    result = generate_answer("문서 설명", [doc], language=language, structured_llm=StubLLM(error=TimeoutError("private data")))
    assert result.answer == TEXT[language]["llm_timeout"]
    assert "private" not in result.model_dump_json()


def test_existing_hit_adapter_uses_only_validated_source_metadata():
    doc = synthetic_msds()
    response = generate("가상 제품 자료 설명", [hit(doc)], "ko", product_id=PRODUCT_ID,
                        structured_llm=StubLLM(synthetic_draft(doc)))
    assert response.sources[0].model_dump() == {
        "doc_id": doc.metadata["doc_id"], "section": doc.metadata["section"],
        "title": doc.metadata["title"], "url": doc.metadata["source_url"],
    }
    assert set(response.model_dump()) == {"answer", "sources", "needs_review", "handoff", "latency_ms"}


def test_unknown_doc_id_is_not_replaced_with_chunk_id():
    doc = synthetic_msds(); doc.metadata.pop("doc_id")
    llm = StubLLM(error=AssertionError("no call"))
    response = generate("자료 설명", [hit(doc)], "ko", product_id=PRODUCT_ID, structured_llm=llm)
    assert response.sources == [] and response.needs_review
    assert not llm.calls


@pytest.mark.parametrize("kwargs", [{"language": "ja"}, {"mode": "approve"}, {"product_id": ""}])
def test_invalid_internal_options_raise(kwargs):
    with pytest.raises(ValueError): generate_answer("자료 설명", [], **kwargs)


def test_conflicting_requested_concentration_defers():
    doc = synthetic_msds()
    result = generate_answer("이 제품 50% 자료를 설명해줘", [doc], product_id=PRODUCT_ID,
                             structured_llm=StubLLM(synthetic_draft(doc)))
    assert result.review_reasons == ["product_unverified"]


def test_real_faiss_results_to_generation_with_test_embeddings_and_mock_llm(monkeypatch):
    from langchain_community.vectorstores import FAISS
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from rag import generator, retriever
    doc = synthetic_msds()
    store = FAISS.from_documents([doc], DeterministicFakeEmbedding(size=16))
    monkeypatch.setattr(retriever, "get_store", lambda topic: store)
    monkeypatch.setattr(generator, "build_document_llm", lambda *a, **k: StubLLM(synthetic_draft(doc)))
    req = RagRequest(question="가상 제품 설명", topic="chemical_safety", product_id=PRODUCT_ID)
    hits = retriever.retrieve(req.question, req.topic, req.product_id, language=req.language)
    response = generate(req.question, hits, req.language, product_id=req.product_id, topic=req.topic)
    assert response.sources[0].doc_id == doc.metadata["doc_id"]
    assert "TrainingLiquid-A" in response.answer and response.needs_review


@pytest.mark.parametrize("change", ["partial_number", "wrong_label", "value_without_label"])
def test_product_fact_value_and_label_validation(change):
    doc = synthetic_msds(); draft = synthetic_draft(doc)
    fact = draft["product_facts"][2]
    if change == "partial_number": fact["value"] = "0%"
    if change == "wrong_label":
        fact["field"] = "product_number"
        draft["product_facts"][1]["field"] = "concentration"
    if change == "value_without_label": fact["citations"][0]["quote"] = "1.0%"
    result, _ = call(doc, output=draft)
    if change == "value_without_label":
        # The concentration label is present in the same cited chunk.
        assert result.sources and "농도: 1.0%" in result.answer
        assert result.review_reasons == ["msds_applicability_unverified"]
    else:
        assert result.review_reasons == ["product_unverified"]


@pytest.mark.parametrize("prohibition", ["请勿将此资料用于真实现场作业。", "切勿将此资料用于真实现场作业。"])
def test_equivalent_chinese_prohibition_is_not_falsely_rejected(prohibition):
    doc = synthetic_msds(); draft = synthetic_draft(doc, "zh")
    draft["critical_translations"][0]["text"] = prohibition
    result, _ = call(doc, "zh", output=draft)
    assert result.sources


@pytest.mark.parametrize("number,accepted", [("两个", True), ("二个", True), ("三个", False), ("十二个", False)])
def test_chinese_equivalent_integer_count_is_valid_but_wrong_count_is_not(number, accepted):
    doc = synthetic_msds(); draft = synthetic_draft(doc, "zh")
    draft["critical_translations"][1]["text"] = f"适用范围是{number}虚拟教育室。"
    result, _ = call(doc, "zh", output=draft)
    assert bool(result.sources) is accepted


def test_metadata_cannot_be_forged_into_a_page_content_citation():
    doc = synthetic_msds(); doc.metadata["jurisdiction"] = "US only"
    draft = synthetic_draft(doc)
    draft["statements"][0]["conditions"][0]["citations"][0]["quote"] = "jurisdiction: US only"
    result, _ = call(doc, output=draft)
    assert result.review_reasons == ["invalid_evidence"]


@pytest.mark.parametrize("language,question,mode", [
    ("ko", "작업 전 자료에서 확인할 내용을 정리해줘", "precheck"),
    ("zh", "请整理作业前需要确认的资料", "precheck"),
    ("vi", "Trước khi làm việc cần kiểm tra thông tin gì?", "precheck"),
    ("ko", "신입에게 쉽게 설명해줘", "learn"),
    ("zh", "请给新员工简单说明", "learn"),
    ("vi", "Giải thích cho nhân viên mới", "learn"),
])
def test_existing_question_field_can_select_learning_or_precheck(language, question, mode):
    doc = synthetic_msds()
    result = generate_answer(question, [doc], language=language, product_id=PRODUCT_ID,
                             structured_llm=StubLLM(synthetic_draft(doc, language)))
    assert result.answer.startswith(TEXT[language][mode])
    if mode == "precheck": assert "precheck_requires_review" in result.review_reasons


@pytest.mark.parametrize("language,translated", [("zh", "实际工作场所适用。"), ("vi", "Áp dụng cho nơi làm việc thực tế.")])
def test_translation_cannot_reverse_an_exclusion(language, translated):
    doc = synthetic_msds(); draft = synthetic_draft(doc, language)
    draft["critical_translations"][-1]["text"] = translated
    result, _ = call(doc, language, output=draft)
    assert result.review_reasons == ["invalid_translation"]


@pytest.mark.parametrize("original,translated,valid", [
    ("경고: 가상 수치 10 ppm", "警告：虚拟数值10%", False),
    ("경고: 가상 수치 10 ppm", "警告：虚拟数值10 ppm", True),
    ("경고: 가상 수치 -10 ℃", "警告：虚拟数值10°C", False),
    ("경고: 가상 수치 -10 ℃", "警告：虚拟数值-10°C", True),
])
def test_translation_preserves_measurement_unit_and_sign(original, translated, valid):
    from rag.prompt import translation_valid
    assert translation_valid(original, translated, "zh") is valid
