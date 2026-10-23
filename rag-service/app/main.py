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
CORS_OPTIONS = {
    "allow_origins": ["http://localhost:5174", "http://127.0.0.1:5174"],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type"],
}

app = FastAPI(
    title="ChemBridge RAG API",
    description=(
        "화학물질 안전·중대재해 법령 다국어 안내 API입니다. "
        f"지원 언어: {', '.join(LANGUAGES)}.\n\n"
        "Java POST http://localhost:8080/api/login 에 username/password를 "
        "application/x-www-form-urlencoded 형식으로 보내면 accessToken이 반환됩니다. "
        "Swagger의 Authorize에 토큰 값만 입력하거나 Authorization: Bearer <JWT> 헤더로 요청하세요. "
        "로그인 화면은 http://localhost:8080/login, 로그인 후 이동 주소는 "
        "Vue 개발 서버 http://localhost:5174/ 입니다.\n\n"
        "기존 HttpOnly ACCESS_TOKEN 쿠키도 호환합니다. Bearer 헤더가 있으면 우선 검증하며, "
        "잘못된 Bearer를 쿠키로 우회하지 않습니다. 쿠키 사용 시 호스트는 localhost로 맞추세요.\n\n"
        "답변은 참고 안내이며, 개별 법률 판단·비상 상황은 담당자에게 연결합니다."
    ),
)

app.add_middleware(CORSMiddleware, **CORS_OPTIONS)


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
            # 예외로 만든 응답에도 일반 응답과 같은 CORS 정책을 적용한다.
            await CORSMiddleware(response, **CORS_OPTIONS)(scope, receive, capture_status)
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
            "description": "Bearer/쿠키 토큰 없음·만료·위조 또는 발급자 불일치. 잘못된 Bearer는 쿠키로 우회하지 않습니다.",
            "content": {"application/json": {"example": {
                "detail": "토큰이 없거나 만료되었거나 올바르지 않습니다.",
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
