"""FastAPI 진입점 — 담당: 정지우

실행 (rag-service/ 에서):  python -m uvicorn app.main:app --port 8001 --reload
"""
import logging
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # rag-service/.env

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.types import ASGIApp, Message, Receive, Scope, Send  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from rag import stores  # noqa: E402
from rag.chain import answer  # noqa: E402
from rag.schema import LANGUAGES, TOPIC_CHEMICAL, TOPIC_LAW, RagRequest, RagResponse, Source  # noqa: E402

logging.basicConfig(level=logging.INFO)
request_log = logging.getLogger("chembridge.requests")
# 기본 접근 로그에는 쿼리 문자열이 포함되므로 아래 미들웨어로 대체한다.
logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(
    title="ChemBridge RAG API",
    description=(
        "화학물질 안전·중대재해 법령 다국어 안내 API입니다. "
        f"지원 언어: {', '.join(LANGUAGES)}.\n\n"
        "인증은 Java 서버가 발급한 HttpOnly ACCESS_TOKEN 쿠키를 사용합니다. "
        "http://localhost:8080/signup 에서 가입하고 /login 에서 로그인한 뒤 "
        "http://localhost:8001/docs 에서 요청하세요. 모든 주소의 호스트를 localhost로 맞추세요. "
        "Swagger의 쿠키 입력칸 대신 브라우저에 저장된 로그인 쿠키가 전송됩니다.\n\n"
        "답변은 참고 안내이며, 개별 법률 판단·비상 상황은 담당자에게 연결합니다."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestLogMiddleware:
    """본문·쿼리·쿠키·예외 원문 없이 경로·상태코드·처리시간만 기록한다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status_code = 500
        response_started = False

        async def capture_status(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        except Exception:
            # 예외 문자열·traceback에 질문이나 인증 정보가 포함될 수 있다.
            if response_started:
                raise RuntimeError("응답 전송을 완료하지 못했습니다.") from None
            response = JSONResponse(
                status_code=500,
                content={"detail": "요청 처리 중 오류가 발생했습니다."},
            )
            await response(scope, receive, capture_status)
        finally:
            # 등록되지 않은 경로의 사용자 입력도 로그에 남기지 않는다.
            path = getattr(scope.get("route"), "path", "/unmatched")
            request_log.info(
                "path=%s status=%d latency_ms=%.2f",
                path, status_code, (perf_counter() - started) * 1000,
            )


app.add_middleware(RequestLogMiddleware)


@app.on_event("startup")
def _load_indexes() -> None:
    try:
        stores.load_all()
    except Exception:
        # 준비 실패 시에도 /health와 /docs에서 상태를 확인할 수 있게 한다.
        logging.getLogger(__name__).warning("인덱스 준비 실패: /health에서 상태를 확인하세요.")


@app.get(
    "/health",
    summary="서비스·인덱스 준비 상태",
    responses={
        200: {
            "description": "인덱스가 하나 이상 준비됨. 각 topic의 상태는 indexes에서 확인합니다.",
            "content": {"application/json": {"example": {
                "ready": True,
                "indexes": {TOPIC_LAW: True, TOPIC_CHEMICAL: False},
            }}},
        },
        503: {
            "description": "사용 가능한 인덱스가 없음.",
            "content": {"application/json": {"example": {
                "ready": False,
                "indexes": {TOPIC_LAW: False, TOPIC_CHEMICAL: False},
            }}},
        },
    },
)
def health():
    """인증 없이 호출합니다. 전체 준비 상태와 topic별 인덱스 상태를 반환합니다."""
    body = {"ready": stores.is_ready(), "indexes": stores.status()}
    return JSONResponse(body, status_code=200 if body["ready"] else 503)


@app.post(
    "/rag-query",
    response_model=RagResponse,
    summary="근거 기반 다국어 안전 안내",
    responses={
        200: {
            "description": "안내와 출처. 담당자 연결 여부도 함께 확인하세요.",
            "content": {"application/json": {"example": RagResponse(
                answer="검색한 근거를 바탕으로 한 안내가 표시됩니다.",
                sources=[Source(
                    doc_id="L2", section="제2조",
                    title="중대재해 처벌 등에 관한 법률",
                    url="https://www.law.go.kr/",
                )],
            ).model_dump()}},
        },
        401: {
            "description": "ACCESS_TOKEN 쿠키 없음·만료·위조 또는 발급자 불일치.",
            "content": {"application/json": {"example": {
                "detail": "토큰이 만료되었거나 올바르지 않습니다.",
            }}},
        },
        422: {"description": "질문 길이, topic, language 등 요청 형식 오류."},
        503: {
            "description": "인증 설정 미준비 또는 LLM 타임아웃·검색/모델 호출 등 RAG 처리 실패.",
            "content": {"application/json": {"example": {
                "detail": "잠시 후 다시 시도해 주세요.",
            }}},
        },
    },
    openapi_extra={"requestBody": {"content": {"application/json": {"examples": {
        "law": {"summary": "법령 질문", "value": RagRequest(
            question="중대재해법의 기준은?", topic=TOPIC_LAW,
        ).model_dump()},
        "chemical": {"summary": "화학물질 안전 질문", "value": RagRequest(
            question="황산 취급 시 보호구는 무엇인가요?", topic=TOPIC_CHEMICAL,
        ).model_dump()},
    }}}}},
)
def rag_query(req: RagRequest, user: dict = Depends(get_current_user)) -> RagResponse:
    """JWT 검증 후 chain.answer()만 호출합니다. 실패 시 내부 오류 대신 503 안내를 반환합니다."""
    try:
        return answer(req)
    except Exception as e:
        raise HTTPException(status_code=503, detail="잠시 후 다시 시도해 주세요.") from e
