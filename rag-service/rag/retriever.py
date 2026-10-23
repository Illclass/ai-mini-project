"""검색(Retriever) — 담당: 김규빈

생성 담당(generate)과의 약속 (rag/schema.py):
    retrieve(question, topic, product_id, k) -> List[Hit]
    - Hit = {"text": str, "score": float, "metadata": ChunkMeta}
    - score: FAISS L2 거리 (작을수록 질문과 가깝다)
    - 결과가 없으면 빈 리스트 → 생성 쪽은 LLM 을 부르지 않고 "찾을 수 없음"으로 처리한다.

제품·장비 범위 (product_id 또는 equipment_id 가 있을 때)
    - 상위 k 개를 뽑은 뒤 거르면, MSDS 인덱스에 섞인 KOSHA·S1 지침이 자리를 다 차지해 고른 제품이 빠진다.
      그래서 FAISS 안에서 먼저 거른다 (filter + fetch_k = 전체 청크 수).
    - 고른 제품의 MSDS 에서 k - COMMON_SLOTS 개, 공통 문서(product_id 없는 지침·법령)에서 나머지를 채운다.
    - 자료 미등록 장비(제품 목록이 빈 장비)는 공통 문서만 검색한다.
"""
from typing import Callable, List, Optional

from rag import equipment
from rag.query import normalize_question
from rag.schema import DEFAULT_TOP_K, Hit
from rag.stores import get_store

COMMON_SLOTS = 2   # 제품 범위 검색에서 공통 문서(KOSHA·S1 등)에 남겨 둘 자리 수


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
    if ids is None:
        return _search_all(queries, store, k)

    allowed = set(ids)
    product_hits = _search_all(queries, store, k - COMMON_SLOTS,
                               filter=lambda md: md.get("product_id") in allowed) if ids else []
    common_hits = _search_all(queries, store, k - len(product_hits),
                              filter=lambda md: not md.get("product_id"))
    return sorted(product_hits + common_hits, key=lambda h: h["score"])
