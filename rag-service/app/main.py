"""FastAPI 진입점 — 담당: 정지우

실행 (rag-service/ 에서):  python -m uvicorn app.main:app --port 8001 --reload
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # rag-service/.env

from fastapi import Depends, FastAPI, HTTPException, Query, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.openapi.utils import get_openapi  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.types import ASGIApp, Message, Receive, Scope, Send  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from rag import stores  # noqa: E402
from rag.chain import answer  # noqa: E402
from rag.diagnostics import capture_failures, exception_details, result_details, response_headers, HEADER_NAMES  # noqa: E402
from rag.schema import LANGUAGES, TOPIC_CHEMICAL, TOPIC_LAW, RagRequest, RagResponse, Source  # noqa: E402

logging.basicConfig(level=logging.INFO)
request_log = logging.getLogger("chembridge.requests")
latency_log = logging.getLogger("chembridge.latency")
diagnostic_log = logging.getLogger("chembridge.diagnostics")
# 기본 접근 로그에는 쿼리 문자열이 포함되므로 아래 미들웨어로 대체한다.
logging.getLogger("uvicorn.access").disabled = True
CORS_OPTIONS = {
    "allow_origins": ["http://localhost:5174", "http://127.0.0.1:5174"],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type"],
    "expose_headers": list(HEADER_NAMES),
}

app = FastAPI(
    title="ChemBridge RAG API",
    openapi_tags=[
        {"name": "Java 인증", "description": "Java 인증서버(:8080)의 회원가입·로그인·인증 확인·로그아웃 API입니다."},
        {"name": "RAG 안내", "description": "발급받은 Bearer 토큰으로 근거 기반 안내를 요청합니다."},
        {"name": "서비스 상태", "description": "RAG 서비스와 인덱스 준비 상태를 확인합니다."},
    ],
    swagger_ui_parameters={"withCredentials": True, "docExpansion": "list"},
    description=(
        "화학물질 안전·중대재해 법령 다국어 안내 API입니다. "
        f"지원 언어: {', '.join(LANGUAGES)}.\n\n"
        "**이 화면에서 테스트하는 순서**\n\n"
        "1. **Java 인증 → POST /api/signup**에서 회원가입합니다. 기존 회원은 건너뜁니다.\n"
        "2. **POST /api/login → Try it out → Execute**로 로그인합니다. "
        "응답 본문의 **accessToken 값만 복사**하세요. 페이지는 이동하지 않습니다.\n"
        "3. 상단 **Authorize**에 토큰 값만 붙여 넣고 **RAG 안내 → POST /rag-query**를 실행합니다.\n"
        "4. 종료 시 **POST /api/logout**을 실행하고 **Authorize → Logout**으로 토큰도 지웁니다.\n\n"
        "Java 인증 항목은 `http://localhost:8080`, RAG 항목은 현재 서버(:8001)를 호출합니다. "
        "외부 클라이언트는 `Authorization: Bearer <JWT>` 헤더로 요청하세요. "
        "로그인 화면은 http://localhost:8080/login, 로그인 후 이동 주소는 "
        "Vue 개발 서버 http://localhost:5174/ 입니다.\n\n"
        "기존 HttpOnly ACCESS_TOKEN 쿠키도 호환합니다. Bearer 헤더가 있으면 우선 검증하며, "
        "잘못된 Bearer를 쿠키로 우회하지 않습니다. 쿠키 사용 시 호스트는 localhost로 맞추세요.\n\n"
        "`equipment_id`는 선택한 가상 장비의 검색 범위를, `product_id`는 실제 제품 범위를 지정합니다. "
        "제품별 MSDS 답변에는 제품 식별·농도·개정일 등의 근거 확인이 필요합니다.\n\n"
        "**HTTP 200은 근거 답변이 생성됐다는 보장이 아닙니다.** "
        "근거 부족·제품 미확인·검증 보류일 때 `sources=[]`, `needs_review=true`, `handoff=true`일 수 있습니다. "
        "프론트는 상태코드와 이 필드를 함께 확인해야 합니다.\n\n"
        "답변은 참고 안내이며, 개별 법률 판단·비상 상황은 담당자에게 연결합니다."
    ),
)

app.add_middleware(CORSMiddleware, **CORS_OPTIONS)


@dataclass
class _LatencyBucket:
    request_count: int = 0
    completed_count: int = 0
    client_error_count: int = 0
    server_error_count: int = 0
    failure_count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    status_counts: dict = field(default_factory=dict)

    def add(self, status: int, elapsed_ms: float, completed: bool) -> None:
        self.request_count += 1
        self.completed_count += int(completed)
        self.client_error_count += int(400 <= status < 500)
        self.server_error_count += int(status >= 500)
        self.failure_count += int(status >= 400 or not completed)
        self.total_ms += elapsed_ms
        self.min_ms = min(self.min_ms, elapsed_ms)
        self.max_ms = max(self.max_ms, elapsed_ms)
        key = str(status)
        self.status_counts[key] = self.status_counts.get(key, 0) + 1

    def snapshot(self) -> dict:
        return {
            "request_count": self.request_count,
            "completed_count": self.completed_count,
            "incomplete_count": self.request_count - self.completed_count,
            "client_error_count": self.client_error_count,
            "server_error_count": self.server_error_count,
            "failure_count": self.failure_count,
            "error_rate": round(self.failure_count / self.request_count, 6) if self.request_count else 0.0,
            "latency_ms": {
                "sum": round(self.total_ms, 2),
                "min": round(self.min_ms, 2) if self.request_count else 0.0,
                "avg": round(self.total_ms / self.request_count, 2) if self.request_count else 0.0,
                "max": round(self.max_ms, 2),
            },
            "status_counts": dict(sorted(self.status_counts.items())),
        }


class LatencyStatistics:
    """프로세스별 HTTP 통계. 원문 없이 누적하며 재시작 시 초기화한다."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._total = _LatencyBucket()
        self._routes: dict = {}
        self._recent_logs: deque = deque(maxlen=1000)
        self._output_path: Path | None = None
        self._write_warning_logged = False

    def enable_file(self, path: Path) -> None:
        with self._lock:
            self._output_path = path

    def _snapshot(self) -> dict:
        return {
            "scope": "http_process_lifetime",
            "pid": os.getpid(),
            "started_at": self._started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "overall": self._total.snapshot(),
            "routes": [
                {"path": path, "method": method, **bucket.snapshot(),
                 "by_status": {str(status): item.snapshot() for status, item in sorted(statuses.items())}}
                for (path, method), (bucket, statuses) in sorted(self._routes.items())
            ],
        }

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def query_logs(self, limit: int, path: str | None, status: int | None) -> dict:
        with self._lock:
            logs = [dict(event) for event in reversed(self._recent_logs)
                    if (path is None or event["path"] == path)
                    and (status is None or event["status"] == status)]
            return {
                **self._snapshot(),
                "filters": {"path": path, "status": status, "limit": limit},
                "retention": {"max_entries": self._recent_logs.maxlen,
                              "retained_count": len(self._recent_logs), "matching_count": len(logs)},
                "logs": logs[:limit],
            }

    def record(self, path: str, method: str, status: int, elapsed_ms: float, completed: bool) -> None:
        method = method if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE", "CONNECT"} else "OTHER"
        with self._lock:
            bucket, statuses = self._routes.setdefault((path, method), (_LatencyBucket(), {}))
            status_bucket = statuses.setdefault(status, _LatencyBucket())
            for item in (self._total, bucket, status_bucket):
                item.add(status, elapsed_ms, completed)
            self._recent_logs.append({
                "sequence": self._total.request_count,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "path": path, "method": method, "status": status,
                "latency_ms": round(elapsed_ms, 2), "completed": completed,
                "level": "ERROR" if status >= 500 or not completed else "WARNING" if status >= 400 else "INFO",
                "outcome": "incomplete" if not completed else "server_error" if status >= 500
                           else "client_error" if status >= 400 else "completed",
            })
            summary = bucket.snapshot()
            latency_log.info(
                "latency_summary path=%s method=%s requests=%d failures=%d avg_ms=%.2f max_ms=%.2f",
                path, method, summary["request_count"], summary["failure_count"],
                summary["latency_ms"]["avg"], summary["latency_ms"]["max"],
            )
            if self._output_path is not None:
                temporary = self._output_path.with_suffix(".tmp")
                try:
                    self._output_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_text(json.dumps(self._snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    temporary.replace(self._output_path)
                    self._write_warning_logged = False
                except OSError:
                    if not self._write_warning_logged:
                        latency_log.warning("지연 통계 파일 기록 실패: 메모리 집계는 유지합니다.")
                        self._write_warning_logged = True


latency_stats = LatencyStatistics()


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
        response_completed = False
        finished: float | None = None

        async def capture_status(message: Message) -> None:
            nonlocal status_code, response_started, response_completed, finished
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_completed = True
                finished = perf_counter()

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
            # CORS preflight는 라우터 전에 끝나므로 등록된 경로만 별도로 확인한다.
            if path == "/unmatched" and scope["path"] in {route.path for route in app.routes}:
                path = scope["path"]
            elapsed_ms = ((finished if finished is not None else perf_counter()) - started) * 1000
            request_log.info(
                "path=%s status=%d latency_ms=%.2f",
                path, status_code, elapsed_ms,
            )
            # 대시보드 조회 자체가 질의 통계·최근 로그를 밀어내지 않게 한다.
            if not (path == "/raq-query-log" and scope["method"] == "GET"):
                latency_stats.record(path, scope["method"], status_code, elapsed_ms, response_completed)


app.add_middleware(RequestLogMiddleware)


@app.on_event("startup")
def _load_indexes() -> None:
    latency_stats.enable_file(Path(__file__).resolve().parents[2] / "logs" / f"rag-latency-{os.getpid()}.json")
    try:
        stores.load_all()
    except Exception:
        # 준비 실패 시에도 /health와 /docs에서 상태를 확인할 수 있게 한다.
        logging.getLogger(__name__).warning("인덱스 준비 실패: /health에서 상태를 확인하세요.")


@app.get(
    "/health",
    tags=["서비스 상태"],
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


@app.get(
    "/raq-query-log",
    tags=["서비스 상태"],
    summary="요청 로그·HTTP 지연 집계 조회",
    responses={
        200: {"description": "overall: 전체 HTTP 집계, routes: 경로·메서드 및 by_status별 집계, logs: 최신순 요청 기록, retention: 보관 범위."},
        401: {"description": "유효한 Bearer 또는 기존 ACCESS_TOKEN 쿠키 필요."},
        422: {"description": "limit(1~1000), status(100~599), 등록된 path 또는 /unmatched만 허용."},
        503: {"description": "인증 설정 미준비."},
    },
)
def rag_query_log(
    limit: int = Query(default=100, ge=1, le=1000, description="반환할 최근 요청 수. 최신순."),
    path: str | None = Query(default=None, max_length=200, description="최근 logs만 필터. 예: /rag-query. 생략하면 전체 경로."),
    status: int | None = Query(default=None, ge=100, le=599, description="최근 logs만 HTTP 상태코드로 필터. 예: 503."),
    user: dict = Depends(get_current_user),
):
    """현재 프로세스의 운영 통계와 최근 최대 1000건의 HTTP 요청 기록을 조회합니다.

    로그인한 사용자는 서비스 공통 통계를 봅니다. 사용자별 대화 이력이 아닙니다.
    각 로그에는 sequence·UTC 시각·경로·메서드·상태코드·지연·완료 여부·level·outcome만 있습니다.
    질문/답변·사용자 ID·토큰·쿠키·쿼리·예외 원문·서버 로그 파일 원문은 제공하지 않습니다.
    status/path 필터는 logs에만 적용하며 overall/routes는 프로세스 전체 누적을 유지합니다.
    재시작하면 초기화되고 worker별 통계입니다. 이 GET 조회 요청은 집계에서 제외합니다.
    응답은 no-store이며, LLM 토큰/비용·검색 청크·LLM 호출별 기록은 포함하지 않습니다.
    """
    if path is not None and path not in {"/unmatched", *(route.path for route in app.routes)}:
        raise HTTPException(status_code=422, detail="등록된 API 경로 또는 /unmatched를 지정해 주세요.")
    return JSONResponse(latency_stats.query_logs(limit, path, status), headers={"Cache-Control": "no-store"})


@app.post(
    "/rag-query",
    tags=["RAG 안내"],
    response_model=RagResponse,
    summary="근거 기반 다국어 안전 안내",
    responses={
        200: {
            "description": "안내와 검증된 출처. 검색 근거가 질문에 충분하지 않으면 sources=[]·handoff=true로 보류할 수 있습니다.",
            "content": {"application/json": {"examples": {
                "with_sources": {"summary": "출처 포함 응답의 구조 예시", "value": RagResponse(
                    answer="검색한 근거를 바탕으로 한 안내가 표시됩니다.",
                    sources=[Source(doc_id="L2", section="제2조", title="중대재해 처벌 등에 관한 법률",
                                    url="https://www.law.go.kr/")],
                ).model_dump()},
                "held": {"summary": "근거 부족으로 판단 보류 - HTTP 200", "value": RagResponse(
                    answer="제공된 자료에서 질문에 답할 충분한 근거를 확인하지 못했습니다. 담당자에게 확인하세요.",
                    needs_review=True, handoff=True,
                ).model_dump()},
            }}},
        },
        401: {
            "description": "Bearer/쿠키 토큰 없음·만료·위조 또는 발급자 불일치. 잘못된 Bearer는 쿠키로 우회하지 않습니다.",
            "content": {"application/json": {"example": {
                "detail": "토큰이 없거나 만료되었거나 올바르지 않습니다.",
            }}},
        },
        422: {"description": "질문 길이(2~500자), topic, 지원 언어, product_id/equipment_id 타입, JSON 형식 오류."},
        503: {
            "description": "인증 설정 미준비 또는 체인에서 예외로 전달한 검색·생성 실패. 검증 불가·근거 부족은 200 보류일 수 있습니다.",
            "content": {"application/json": {"example": {
                "detail": "잠시 후 다시 시도해 주세요.",
            }}},
        },
        500: {
            "description": "의존성·응답 검증 등 예상하지 못한 내부 오류. 원시 예외는 노출하지 않습니다.",
            "content": {"application/json": {"example": {"detail": "요청 처리 중 오류가 발생했습니다."}}},
        },
    },
    openapi_extra={"requestBody": {"content": {"application/json": {"examples": {
        "law": {"summary": "법령 질문", "value": RagRequest(
            question="중대재해처벌법 제2조에서 정한 중대산업재해의 정의는 무엇인가요?", topic=TOPIC_LAW,
        ).model_dump()},
        "chemical": {"summary": "제품 MSDS 요청 형식 - 실제 근거 검증 필요", "value": RagRequest(
            question="선택한 제품의 보호구 정보는 어떤 문서에서 확인하나요?", topic=TOPIC_CHEMICAL,
            product_id="sigma-339741", equipment_id="DEMO-WET-01",
        ).model_dump()},
    }}}}},
)
def rag_query(req: RagRequest, response: Response, user: dict = Depends(get_current_user)) -> RagResponse:
    """JWT·요청 검증 후 chain.answer()만 호출합니다. 검색·LLM을 API에서 직접 호출하지 않습니다.

    질문별 독립 요청이며 대화 이력은 전달하지 않습니다. 출처·보류 플래그는 체인 결과를 그대로 반환합니다.
    현재 특정 topic 인덱스 부재는 검색 0건과 같은 200 보류일 수 있습니다. 준비 장애 503 구분은 공동 계약 대기입니다.
    """
    request_id = uuid4().hex
    # Keep the JSON body/status contract. Only bounded diagnostics are exposed
    # in headers; prompts, user identity, tokens and raw exceptions stay private.
    with capture_failures() as failures:
        try:
            result = answer(req)
        except Exception as error:
            details = failures[-1] if failures else exception_details(error, stage="chain")
            reason = getattr(error, "reason", None)
            if reason in {"llm_timeout", "llm_error", "configuration_error"}:
                details.setdefault("reason", reason)
            diagnostic_log.warning(json.dumps({"request_id": request_id, "http_status": 503,
                                               **details}, ensure_ascii=False, sort_keys=True))
            raise HTTPException(status_code=503, detail="잠시 후 다시 시도해 주세요.",
                                headers=response_headers(details, request_id)) from None
        details = failures[-1] if failures else result_details(result)
        response.headers.update(response_headers(details, request_id))
        if details["category"] != "answer":
            diagnostic_log.info(json.dumps({"request_id": request_id, "http_status": 200,
                                            **details}, ensure_ascii=False, sort_keys=True))
        return result


def _java_auth_paths() -> dict:
    """Java API를 같은 명세에 표시하고 실제 요청은 Java 서버로 직접 보낸다."""
    credentials = {
        "type": "object",
        "required": ["username", "password"],
        "properties": {
            "username": {"type": "string", "minLength": 1, "description": "회원 아이디"},
            "password": {"type": "string", "format": "password", "minLength": 1, "description": "비밀번호"},
        },
    }
    success = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    json_error = {"type": "object", "required": ["ok", "error"],
                  "properties": {"ok": {"type": "boolean"}, "error": {"type": "string"}}}
    text_error = {"text/plain": {"schema": {"type": "string"}}}
    form_redirect = {"description": "JSON 응답을 요청하지 않은 웹 폼: /login으로 이동",
                     "headers": {"Location": {"schema": {"type": "string"}, "example": "/login"}}}
    login = {
        "type": "object",
        "required": ["ok", "redirect", "accessToken", "tokenType", "expiresIn"],
        "properties": {
            "ok": {"type": "boolean"},
            "redirect": {"type": "string", "example": "http://localhost:5174/"},
            "accessToken": {"type": "string", "description": "이 값을 복사해 상단 Authorize에 붙여 넣습니다."},
            "tokenType": {"type": "string", "example": "Bearer"},
            "expiresIn": {"type": "integer", "example": 3600},
        },
    }

    def operation(operation_id, summary, description, responses, *, form=False, protected=False):
        result = {
            "operationId": operation_id,
            "tags": ["Java 인증"],
            "summary": summary,
            "description": description,
            "servers": [{"url": "http://localhost:8080", "description": "Java 인증서버"}],
            "security": [{"BearerAuth": []}] if protected else [],
            "responses": responses,
        }
        if form:
            result["requestBody"] = {
                "required": True,
                "content": {"application/x-www-form-urlencoded": {"schema": credentials}},
            }
        return result

    return {
        "/api/signup": {"post": operation(
            "java_signup", "회원가입", "새 회원을 등록합니다. 성공 후 아래 로그인 API를 실행하세요.",
            {
                "201": {"description": "회원가입 완료", "content": {"application/json": {"schema": success}}},
                "302": form_redirect,
                "400": {"description": "아이디·비밀번호 누락 또는 중복 아이디", "content": text_error},
                "500": {"description": "회원 저장 실패", "content": text_error},
            }, form=True,
        )},
        "/api/login": {"post": operation(
            "java_login", "로그인 · Bearer 토큰 발급",
            "회원 아이디와 비밀번호를 입력하고 Execute를 누르세요. "
            "200 응답 본문의 accessToken 값만 복사해 상단 Authorize에 붙여 넣습니다. "
            "redirect 필드는 웹 화면용이며 Swagger에서는 페이지를 이동하지 않습니다.",
            {
                "200": {"description": "로그인 성공 · accessToken 복사", "content": {"application/json": {"schema": login}}},
                "400": {"description": "아이디·비밀번호 누락", "content": {"application/json": {"schema": json_error}}},
                "401": {"description": "로그인 정보 불일치", "content": {"application/json": {"schema": json_error}}},
                "500": {"description": "인증서버 처리 실패", "content": {"application/json": {"schema": json_error}}},
            }, form=True,
        )},
        "/api/auth/check": {"get": operation(
            "java_auth_check", "현재 인증 확인", "Authorize에 입력한 Bearer 토큰 또는 기존 로그인 쿠키의 인증 상태를 확인합니다.",
            {
                "200": {"description": "인증 성공", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"}, "via": {"type": "string"},
                        "username": {"type": "string"}, "sub": {"type": "string"},
                    },
                }}}},
                "401": {"description": "토큰 없음·만료·위조 또는 잘못된 Bearer"},
            }, protected=True,
        )},
        "/api/logout": {"post": operation(
            "java_logout", "로그아웃",
            "로그인 쿠키와 서버 세션을 삭제합니다. 실행 후 상단 Authorize → Logout으로 "
            "Swagger에 보관한 Bearer도 직접 지우세요. 이미 복사한 JWT는 만료 전까지 유효합니다.",
            {"200": {"description": "쿠키·세션 로그아웃 완료", "content": {"application/json": {"schema": success}}},
             "302": form_redirect},
        )},
    }


def _combined_openapi() -> dict:
    if app.openapi_schema is None:
        schema = get_openapi(
            title=app.title, version=app.version, openapi_version=app.openapi_version,
            description=app.description, routes=app.routes, tags=app.openapi_tags,
        )
        schema["paths"].update(_java_auth_paths())
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _combined_openapi
