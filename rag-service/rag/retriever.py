"""검색(Retriever) — 담당: 김규빈

생성 담당(generate)과의 약속 (rag/schema.py):
    retrieve(question, topic, product_id, k) -> List[Hit]
    - Hit = {"text": str, "score": float, "metadata": ChunkMeta}
    - score: FAISS L2 거리 (작을수록 질문과 가깝다)
    - 결과가 없으면 빈 리스트 → 생성 쪽은 LLM 을 부르지 않고 "찾을 수 없음"으로 처리한다.
"""
from typing import List, Optional

from rag.query import normalize_question
from rag.schema import DEFAULT_TOP_K, Hit
from rag.stores import get_store


def search_store(question: str, vectorstore, k: int = DEFAULT_TOP_K) -> List[Hit]:
    """인덱스 하나에서 질문과 가까운 청크 상위 k개 (거리 오름차순). 기존 템플릿이 사용 중."""
    if vectorstore is None or not question.strip():
        return []

    docs_scores = vectorstore.similarity_search_with_score(question, k=k)

    hits = []
    for doc, score in docs_scores:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        hits.append({"text": text, "score": float(score), "metadata": dict(doc.metadata or {})})
    return hits


def filter_hits(hits: List[Hit], product_id: Optional[str] = None) -> List[Hit]:
    """product_id 가 있으면 그 제품 MSDS 청크만 남긴다."""
    if not product_id:
        return hits
    return [h for h in hits if h["metadata"].get("product_id") == product_id]


def retrieve(question: str, topic: str, product_id: Optional[str] = None,
             k: int = DEFAULT_TOP_K, language: str = "ko") -> List[Hit]:
    """stores.get_store(topic) → query.normalize_question 결과마다 search_store → 중복 제거 → filter_hits → 상위 k."""
    store = get_store(topic)
    if store is None:
        return []

    # product_id 필터로 걸러질 것을 감안해 넉넉히 가져온다
    fetch_k = k * 4 if product_id else k

    best = {}
    for q in normalize_question(question, language):
        for h in search_store(q, store, k=fetch_k):
            key = h["metadata"].get("chunk_id") or h["text"]
            if key not in best or h["score"] < best[key]["score"]:
                best[key] = h

    hits = sorted(best.values(), key=lambda h: h["score"])
    return filter_hits(hits, product_id)[:k]
