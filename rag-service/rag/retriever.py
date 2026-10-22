"""검색(Retriever) 담당 모듈.

생성 담당(generate)과의 약속:
    retrieve(question, vectorstore, k) -> [{"text": str, "score": float, "metadata": dict}, ...]
    - score: FAISS L2 거리 (작을수록 질문과 가깝다)
    - metadata: 적재 스크립트가 붙인 값 (law_name, article_no, source_url, doc_type, chunk_id ...)
    - 결과가 없으면 빈 리스트 → 호출 쪽은 LLM을 부르지 않고 "찾을 수 없음"으로 처리한다.
"""
from typing import Any, Dict, List


def retrieve(question: str, vectorstore, k: int = 5) -> List[Dict[str, Any]]:
    """질문과 가까운 청크 상위 k개를 거리 오름차순으로 돌려준다."""
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
