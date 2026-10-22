"""FastAPI 진입점 — 담당: 정지우

실행 (rag-service/ 에서):  python -m uvicorn app.main:app --port 8001 --reload
"""
from fastapi import Depends, FastAPI

from app.auth import get_current_user
from rag.chain import answer
from rag.schema import RagRequest, RagResponse

app = FastAPI(title="ChemBridge RAG API")


@app.get("/health")
def health() -> dict:
    """서비스·인덱스 준비 여부. 준비 완료 200, 미준비 503."""
    # TODO: rag.stores 의 인덱스 로드 상태를 확인해 미준비면 503
    raise NotImplementedError


@app.post("/rag-query", response_model=RagResponse)
def rag_query(req: RagRequest, user: dict = Depends(get_current_user)) -> RagResponse:
    """JWT 검증 후 chain.answer() 호출. 타임아웃·모델 미준비는 503."""
    # TODO: 예외 처리(503), 로그(경로·상태·지연·토큰 — 질문 원문 저장 금지)
    return answer(req)
