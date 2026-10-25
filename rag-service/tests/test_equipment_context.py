"""B equipment-context regression checks: no indexes, keys, or network."""
from types import SimpleNamespace
import pytest
from langchain_core.documents import Document
from rag import retriever
from rag.schema import TOPIC_CHEMICAL, TOPIC_LAW


def doc(cid, text="original source", product=None, doc_type="guide"):
    md={"chunk_id":cid,"doc_id":cid.split("-")[0],"doc_type":doc_type}
    if product: md["product_id"]=product
    return Document(page_content=text,metadata=md)


class Store:
    def __init__(self, documents):
        self.documents=documents
        self.docstore=SimpleNamespace(_dict={str(i):d for i,d in enumerate(documents)})
        self.index=SimpleNamespace(ntotal=len(documents))
    def similarity_search_with_score(self, question, k, **kwargs):
        predicate=kwargs.get("filter")
        return [(d,float(i)) for i,d in enumerate(self.documents)
                if predicate is None or predicate(d.metadata)][:k]


@pytest.fixture
def setup(monkeypatch):
    docs=[doc("S1-12_3","wrong equipment procedure"),
          doc("D1-s8","actual sulfuric PPE", "sigma-339741","msds"),
          doc("D2-s8","other product PPE", "sigma-695068","msds"),
          doc("S1-16","shared equipment table"), doc("K1-4_1","shared storage guide"),
          doc("S1-3_3","Wet Bench precheck"), doc("S1-3_5","Wet Bench emergency reference"),
          doc("S1-2_2","shared isolation reference")]
    store=Store(docs)
    monkeypatch.setattr(retriever,"get_store",lambda topic:store)
    monkeypatch.setattr(retriever,"normalize_question",lambda q,lang,topic:[q])
    monkeypatch.setattr(retriever,"DROP_TRUNCATED",False)
    monkeypatch.setattr(retriever,"ATTACH_IDENTITY",False)
    monkeypatch.setattr(retriever.equipment,"get",lambda eid:{"basis":"S1 3장, K7", "product_ids":[]} if eid=="wet" else None)
    return store


@pytest.mark.parametrize("question",[
    "Wet Bench에서 황산을 사용하기 전 잔류 약액과 공급라인 상태는 어떻게 점검하나요?",
    "Wet Bench의 황산 공급 차단과 신고 절차는 어느 현장 지침에 나와 있나요?",
    "How do I find the selected equipment's documents?",
])
def test_selected_equipment_sources_survive_top_k_without_cross_equipment_or_product(question,setup):
    hits=retriever.retrieve(question,TOPIC_CHEMICAL,"sigma-339741",k=2,equipment_id="wet")
    ids=[h["metadata"]["chunk_id"] for h in hits]
    assert {"D1-s8","S1-16","S1-3_3","S1-3_5"} <= set(ids)
    assert "S1-12_3" not in ids and "D2-s8" not in ids
    originals={d.metadata["chunk_id"]:d for d in setup.documents}
    assert len(ids)==len(set(ids))
    for hit in hits:
        source=originals[hit["metadata"]["chunk_id"]]
        assert hit["text"]==source.page_content and hit["metadata"]==source.metadata


def test_no_equipment_preserves_unscoped_results(setup):
    hits=retriever.retrieve("황산 자료",TOPIC_CHEMICAL,"sigma-339741",k=2)
    assert [h["metadata"]["chunk_id"] for h in hits]==["S1-12_3","D1-s8"]


def test_unknown_equipment_preserves_unscoped_results(setup):
    hits=retriever.retrieve("황산 자료",TOPIC_CHEMICAL,"sigma-339741",k=2,equipment_id="unknown")
    assert [h["metadata"]["chunk_id"] for h in hits]==["S1-12_3","D1-s8"]


def test_law_topic_does_not_attach_chemical_site_context(setup):
    hits=retriever.retrieve("법령 정의",TOPIC_LAW,"sigma-339741",k=2,equipment_id="wet")
    assert [h["metadata"]["chunk_id"] for h in hits]==["S1-12_3","D1-s8"]


def test_shared_guides_remain_and_existing_selected_documents_are_not_duplicated(setup):
    hits=retriever.retrieve("보관 자료",TOPIC_CHEMICAL,"sigma-339741",k=8,equipment_id="wet")
    ids=[h["metadata"]["chunk_id"] for h in hits]
    assert {"K1-4_1","S1-2_2","S1-16","S1-3_3","S1-3_5"} <= set(ids)
    assert len(ids)==len(set(ids)) and "S1-12_3" not in ids


@pytest.mark.parametrize("basis",[None,"",{},"K7 only","S1 0장","S1 17장","S1 999장"])
def test_missing_or_out_of_range_basis_preserves_old_behavior(setup,monkeypatch,basis):
    monkeypatch.setattr(retriever.equipment,"get",lambda eid:{"basis":basis})
    hits=retriever.retrieve("황산 자료",TOPIC_CHEMICAL,"sigma-339741",k=2,equipment_id="wet")
    assert [h["metadata"]["chunk_id"] for h in hits]==["S1-12_3","D1-s8"]


@pytest.mark.parametrize("cid", [None, 3, ["S1-3_7"], "S1-3_bad", "S1-3_3 trailing"])
def test_malformed_site_chunk_id_is_not_attached(setup, cid):
    bad=doc("S1-3_7");bad.metadata["chunk_id"]=cid
    setup.docstore._dict={"bad":bad}
    hits=[{"text":"original common guide","score":1.0,"metadata":{"chunk_id":"K1-1"}}]
    assert retriever.attach_equipment_context(hits,setup,3)==hits


@pytest.mark.parametrize("change", [
    {"page_content":"  "}, {"doc_type":"msds"}, {"product_id":"other-product"},
])
def test_empty_or_product_specific_documents_not_added_as_site_context(setup,change):
    bad=doc("S1-3_7")
    for key,value in change.items():
        if key=="page_content":bad.page_content=value
        else:bad.metadata[key]=value
    setup.docstore._dict={"bad":bad}
    hits=[{"text":"common guide","score":1.0,"metadata":{"chunk_id":"K1-1"}}]
    assert retriever.attach_equipment_context(hits,setup,3)==hits


def test_conflicting_site_chunk_ids_are_not_arbitrarily_selected(setup):
    setup.docstore._dict={"a":doc("S1-3_7","first"),"b":doc("S1-3_7","conflicting")}
    hits=[{"text":"common guide","score":1.0,"metadata":{"chunk_id":"K1-1"}}]
    assert retriever.attach_equipment_context(hits,setup,3)==hits


@pytest.mark.parametrize("documents",[
    [doc(f"S1-3_{n}") for n in range(20)],
    [doc("S1-3_7", "source warning. "*2000)],
])
def test_oversized_chapter_not_partially_copied_or_truncated(setup,documents):
    setup.docstore._dict={str(n):d for n,d in enumerate(documents)}
    hits=[{"text":"common guide","score":1.0,"metadata":{"chunk_id":"K1-1"}}]
    assert retriever.attach_equipment_context(hits,setup,3)==hits


def test_no_original_hits_does_not_manufacture_equipment_answer(setup):
    assert retriever.attach_equipment_context([],setup,3)==[]


def test_ambiguous_equipment_mapping_preserves_prior_scope(setup,monkeypatch):
    monkeypatch.setattr(retriever.equipment,"get",lambda eid:{"basis":"S1 3장, S1 4장"})
    hits=retriever.retrieve("황산 자료",TOPIC_CHEMICAL,"sigma-339741",k=2,equipment_id="wet")
    assert [h["metadata"]["chunk_id"] for h in hits]==["S1-12_3","D1-s8"]


def test_equipment_without_selected_product_does_not_add_msds(setup):
    hits=retriever.retrieve("장비 자료",TOPIC_CHEMICAL,k=2,equipment_id="wet")
    assert {"S1-3_3","S1-3_5"}<={h["metadata"]["chunk_id"] for h in hits}
    assert all(h["metadata"].get("doc_type")!="msds" for h in hits)
