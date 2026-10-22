"""FastAPI 진입점 — 담당: 정지우

실행 (rag-service/ 에서):  python -m uvicorn app.main:app --port 8001 --reload
"""
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # rag-service/.env

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from rag import stores  # noqa: E402
from rag.chain import answer  # noqa: E402
from rag.schema import RagRequest, RagResponse  # noqa: E402

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ChemBridge RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],  # Vue 프론트
    allow_credentials=True,   # ACCESS_TOKEN 쿠키
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _load_indexes() -> None:
    stores.load_all()


@app.get("/health")
def health():
    """서비스·인덱스 준비 여부. 준비 완료 200, 미준비 503."""
    body = {"ready": stores.is_ready(), "indexes": stores.status()}
    return JSONResponse(body, status_code=200 if body["ready"] else 503)


@app.post("/rag-query", response_model=RagResponse)
def rag_query(req: RagRequest, user: dict = Depends(get_current_user)) -> RagResponse:
    """JWT 검증 후 chain.answer() 호출. 타임아웃·모델 미준비는 503."""
    # TODO: 로그(경로·상태·지연·토큰 — 질문 원문 저장 금지)
    try:
        return answer(req)
    except Exception as e:  # LLM 타임아웃·인덱스 오류 등
        logging.exception("rag-query 실패")
        raise HTTPException(status_code=503, detail="잠시 후 다시 시도해 주세요.") from e
