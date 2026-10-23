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
    - 화학 질문인데 제품이 정해지지 않으면(물질명 없음·장비 없음) MSDS 는 빼고 공통 문서만 검색한다.
      생성 쪽은 product_id 없이 MSDS 가 섞이면 바로 "제품 확인 필요"로 보류하므로, 지침·현장지침·법령으로 답하게 한다.

잘린 MSDS 청크 제외 (DROP_TRUNCATED)
    - 생성 쪽은 MSDS 근거 중 하나라도 경고 문맥이 잘렸으면(prompt.incomplete_critical_chunks) 답변 전체를 보류한다.
      실제 MSDS 는 목록·표 형식이 많아 청크의 약 1/3 이 잘림으로 판정되므로, 그 청크만 근거에서 빼고 다음 순위로 채운다.
    - 대가: 빠진 청크 안의 경고는 답변에 나오지 않는다 (생성 쪽 MSDS 원문 확인 안내는 그대로 붙는다).

제품 식별 근거 붙이기 (ATTACH_IDENTITY)
    - 생성 쪽은 MSDS 로 답하기 전에 제품명·제품번호·농도·개정일을 원문 인용으로 확인한다.
      이 값들은 MSDS 1항(제품명·번호) · 3항(함유량) · 16항(최종 개정일자)에 있어 보호구·취급 질문으로는 검색되지 않는다.
    - 제품이 하나로 정해졌으면 그 제품의 해당 청크를 상위 k 개 뒤에 덧붙인다 (k 개 밖, 이미 있으면 생략).
"""
import re
from typing import Callable, List, Optional

from rag import equipment
from rag.query import normalize_question
from rag.schema import DEFAULT_TOP_K, DOC_TYPE_MSDS, TOPIC_CHEMICAL, Hit
from rag.stores import get_store

MIN_PRODUCT = 2    # 제품 범위 검색에서 고른 제품 MSDS 를 최소 몇 개 넣을지
DROP_TRUNCATED = True   # 경고 문맥이 잘린 MSDS 청크를 근거에서 뺀다 (모듈 설명 참고)
TRUNCATED_MARGIN = 4    # 빠질 청크를 대비해 더 가져올 개수
ATTACH_IDENTITY = True  # 제품이 하나로 정해지면 MSDS 1·3·16항 식별 청크를 덧붙인다 (모듈 설명 참고)
# MSDS 항목 번호 → 그 항목 청크 중 식별 정보가 있는 청크를 고르는 표시
IDENTITY_SECTIONS = {1: r"제품\s*번호", 3: r"함유량|농도", 16: r"최종\s*개정"}


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
    """질문 여러 개(동의어 확장)로 검색 → 청크마다 변형 질문 중 가장 좋은 순위로 정렬(같으면 거리) → 상위 k.
    거리 최솟값으로 합치면 원문 질문에 조금 더 가까운 청크가 이겨서 동의어 변형이 1위로 찾은 정답이 밀려난다.
    예) "중대재해법의 기준은?" → 변형 "…정의은?" 에서 제2조 1위인데 거리로 합치면 7위 (70문항 비교: hit@5 96→97%)"""
    best, best_rank = {}, {}
    for q in queries:
        for rank, h in enumerate(search_store(q, store, k=k, filter=filter), start=1):
            key = h["metadata"].get("chunk_id") or h["text"]
            if key not in best or h["score"] < best[key]["score"]:
                best[key] = h
            best_rank[key] = min(best_rank.get(key, rank), rank)
    ranked = sorted(best, key=lambda key: (best_rank[key], best[key]["score"]))
    return [best[key] for key in ranked[:k]]


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


_IDENTITY_CACHE: dict = {}   # (인덱스 id, product_id) → 식별 청크 목록


def identity_chunks(store, product_id: str) -> list:
    """제품의 식별 청크: 1·3·16항마다 식별 표시(IDENTITY_SECTIONS)가 있는 첫 청크."""
    key = (id(store), product_id)
    if key not in _IDENTITY_CACHE:
        docs = sorted((d for d in store.docstore._dict.values() if d.metadata.get("product_id") == product_id),
                      key=lambda d: d.metadata.get("chunk_id", ""))
        picked = []
        for no, mark in IDENTITY_SECTIONS.items():
            doc = next((d for d in docs if d.metadata.get("msds_section_no") == no
                        and re.search(mark, d.page_content)), None)
            if doc is not None:
                picked.append(doc)
        _IDENTITY_CACHE[key] = picked
    return _IDENTITY_CACHE[key]


def attach_identity(hits: List[Hit], store, product_id: Optional[str]) -> List[Hit]:
    """제품이 하나로 정해졌으면 식별 청크를 hits 뒤에 덧붙인다 (이미 있는 청크·잘림 판정 청크는 제외)."""
    if not ATTACH_IDENTITY or not product_id or store is None:
        return hits
    have = {h["metadata"].get("chunk_id") for h in hits}
    worst = max((h["score"] for h in hits), default=0.0)
    extra = [{"text": d.page_content, "score": worst, "metadata": dict(d.metadata)}
             for d in identity_chunks(store, product_id) if d.metadata.get("chunk_id") not in have]
    return hits + drop_truncated(extra)


def scope_product_ids(product_id: Optional[str], equipment_id: Optional[str]) -> Optional[List[str]]:
    """검색할 제품 범위. product_id 가 우선, 없으면 장비의 제품 목록. None 이면 범위 제한 없음."""
    if product_id:
        return [product_id]
    return equipment.product_ids(equipment_id)


def retrieve(question: str, topic: str, product_id: Optional[str] = None,
             k: int = DEFAULT_TOP_K, language: str = "ko",
             equipment_id: Optional[str] = None) -> List[Hit]:
    """stores.get_store(topic) → query.normalize_question → (제품 범위가 있으면) 제품 MSDS + 공통 문서 → 상위 k
    → (제품이 하나면) 식별 청크 덧붙임. 그래서 제품이 하나로 정해진 경우 결과가 k 개보다 많을 수 있다."""
    store = get_store(topic)
    if store is None:
        return []

    queries = normalize_question(question, language, topic)
    ids = scope_product_ids(product_id, equipment_id)
    extra = TRUNCATED_MARGIN if DROP_TRUNCATED else 0
    if ids is None:
        if topic == TOPIC_CHEMICAL:   # 제품 미지정 → MSDS 제외 (모듈 설명 참고)
            return _search_all(queries, store, k, filter=lambda md: md.get("doc_type") != DOC_TYPE_MSDS)
        return drop_truncated(_search_all(queries, store, k + extra))[:k]
    single = ids[0] if len(ids) == 1 else None

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
    return attach_identity(sorted(in_scope, key=lambda h: h["score"])[:k], store, single)
