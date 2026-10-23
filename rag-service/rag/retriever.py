"""검색(Retriever) — 담당: 김규빈

생성 담당(generate)과의 약속 (rag/schema.py):
    retrieve(question, topic, product_id, k) -> List[Hit]
    - Hit = {"text": str, "score": float, "metadata": ChunkMeta}
    - score: FAISS L2 거리 (작을수록 질문과 가깝다)
    - 결과가 없으면 빈 리스트 → 생성 쪽은 LLM 을 부르지 않고 "찾을 수 없음"으로 처리한다.

제품·장비 범위 (product_id 또는 equipment_id 가 있을 때)
    - 상위 k 개를 뽑은 뒤 거르면, MSDS 인덱스에 섞인 KOSHA·S1 지침이 자리를 다 차지해 고른 제품이 빠진다.
      그래서 FAISS 안에서 먼저 거른다 (filter + fetch_k = 전체 청크 수).
    - 다른 제품의 MSDS 만 빼고(고른 제품 MSDS + 공통 문서) 순위대로 뽑되, 고른 제품 MSDS 가 MIN_PRODUCT 개보다
      적으면 그 제품 MSDS 에서 채운다. (자리를 고정하면 S1 장비 절차처럼 공통 문서가 필요한 질문이 밀려난다)
    - 자료 미등록 장비(제품 목록이 빈 장비)는 공통 문서만 검색한다.

잘린 MSDS 청크 제외 (DROP_TRUNCATED)
    - 생성 쪽은 MSDS 근거 중 하나라도 경고 문맥이 잘렸으면(prompt.incomplete_critical_chunks) 답변 전체를 보류한다.
      실제 MSDS 는 목록·표 형식이 많아 청크의 약 1/3 이 잘림으로 판정되므로, 그 청크만 근거에서 빼고 다음 순위로 채운다.
    - 대가: 빠진 청크 안의 경고는 답변에 나오지 않는다 (생성 쪽 MSDS 원문 확인 안내는 그대로 붙는다).
"""
from typing import Callable, List, Optional

from rag import equipment
from rag.query import normalize_question
from rag.schema import DEFAULT_TOP_K, DOC_TYPE_MSDS, Hit
from rag.stores import get_store

MIN_PRODUCT = 2    # 제품 범위 검색에서 고른 제품 MSDS 를 최소 몇 개 넣을지
DROP_TRUNCATED = True   # 경고 문맥이 잘린 MSDS 청크를 근거에서 뺀다 (모듈 설명 참고)
TRUNCATED_MARGIN = 4    # 빠질 청크를 대비해 더 가져올 개수


def search_store(question: str, vectorstore, k: int = DEFAULT_TOP_K,
                 filter: Optional[Callable[[dict], bool]] = None) -> List[Hit]:
    """인덱스 하나에서 질문과 가까운 청크 상위 k개 (거리 오름차순). filter 가 있으면 FAISS 안에서 먼저 거른다."""
    if vectorstore is None or not question.strip() or k <= 0:
        return []

    kwargs = {"filter": filter, "fetch_k": vectorstore.index.ntotal} if filter else {}
    docs_scores = vectorstore.similarity_search_with_score(question, k=k, **kwargs)

    hits = []
    for doc, score in docs_scores:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        hits.append({"text": text, "score": float(score), "metadata": dict(doc.metadata or {})})
    return hits


def _search_all(queries: List[str], store, k: int, filter=None) -> List[Hit]:
    """질문 여러 개(동의어 확장)로 검색 → chunk_id 중복 제거(가장 가까운 점수) → 상위 k.
    (순위 융합 RRF 도 비교했지만 70문항에서 차이가 1~2문항이라 단순한 쪽을 쓴다)"""
    best = {}
    for q in queries:
        for h in search_store(q, store, k=k, filter=filter):
            key = h["metadata"].get("chunk_id") or h["text"]
            if key not in best or h["score"] < best[key]["score"]:
                best[key] = h
    return sorted(best.values(), key=lambda h: h["score"])[:k]


def drop_truncated(hits: List[Hit]) -> List[Hit]:
    """경고 문맥이 잘렸다고 판정된 MSDS 청크를 뺀다 (판정 기준은 생성 쪽 prompt.incomplete_critical_chunks)."""
    if not DROP_TRUNCATED:
        return hits
    from langchain_core.documents import Document
    from rag.prompt import incomplete_critical_chunks  # 생성 쪽 판정을 그대로 쓴다 (기준이 어긋나지 않도록)

    msds = [Document(page_content=h["text"], metadata=h["metadata"]) for h in hits
            if h["metadata"].get("doc_type") == DOC_TYPE_MSDS]
    bad = set(incomplete_critical_chunks(msds)) if msds else set()
    return [h for h in hits if h["metadata"].get("chunk_id") not in bad]


def scope_product_ids(product_id: Optional[str], equipment_id: Optional[str]) -> Optional[List[str]]:
    """검색할 제품 범위. product_id 가 우선, 없으면 장비의 제품 목록. None 이면 범위 제한 없음."""
    if product_id:
        return [product_id]
    return equipment.product_ids(equipment_id)


def retrieve(question: str, topic: str, product_id: Optional[str] = None,
             k: int = DEFAULT_TOP_K, language: str = "ko",
             equipment_id: Optional[str] = None) -> List[Hit]:
    """stores.get_store(topic) → query.normalize_question → (제품 범위가 있으면) 제품 MSDS + 공통 문서 → 상위 k."""
    store = get_store(topic)
    if store is None:
        return []

    queries = normalize_question(question, language, topic)
    ids = scope_product_ids(product_id, equipment_id)
    extra = TRUNCATED_MARGIN if DROP_TRUNCATED else 0
    if ids is None:
        return drop_truncated(_search_all(queries, store, k + extra))[:k]

    allowed = set(ids)
    in_scope = drop_truncated(_search_all(queries, store, k + extra,
                                          filter=lambda md: not md.get("product_id") or md["product_id"] in allowed))[:k]
    n_product = sum(1 for h in in_scope if h["metadata"].get("product_id"))
    if ids and n_product < MIN_PRODUCT:
        have = {h["metadata"].get("chunk_id") for h in in_scope}
        more = [h for h in drop_truncated(_search_all(queries, store, MIN_PRODUCT + extra,
                                                      filter=lambda md: md.get("product_id") in allowed))
                if h["metadata"].get("chunk_id") not in have][:MIN_PRODUCT - n_product]
        common = [h for h in in_scope if not h["metadata"].get("product_id")]
        in_scope = [h for h in in_scope if h["metadata"].get("product_id")] + more + common[:k - n_product - len(more)]
    return sorted(in_scope, key=lambda h: h["score"])[:k]
