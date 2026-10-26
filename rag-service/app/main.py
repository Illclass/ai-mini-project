"""FastAPI 진입점 — 담당: 정지우

실행 (rag-service/ 에서):  python -m uvicorn app.main:app --port 8001 --reload
"""
from collections import Counter, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import httpx
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # rag-service/.env

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.exception_handlers import request_validation_exception_handler  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.openapi.utils import get_openapi  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator  # noqa: E402
from openai import APIError  # noqa: E402
from starlette.types import ASGIApp, Message, Receive, Scope, Send  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from rag import diagnostics, stores  # noqa: E402
from rag.chain import RAGUnavailable, answer  # noqa: E402
from rag.generator import GenerationUnavailable  # noqa: E402
from rag.schema import LANGUAGES, TOPIC_CHEMICAL, TOPIC_LAW, RagRequest, RagResponse, Source  # noqa: E402

logging.basicConfig(level=logging.INFO)
request_log = logging.getLogger("chembridge.requests")
latency_log = logging.getLogger("chembridge.latency")
pipeline_log = logging.getLogger("chembridge.pipeline")
trace_log = logging.getLogger("chembridge.trace")
DIAGNOSTIC_PATH = "/rag-query/diagnostics"
EVALUATION_PATH = "/rag-query/evaluations"
_EVALUATION_ROOT = Path(__file__).resolve().parents[1] / "eval"
_SAFE_PIPELINE_REASONS = diagnostics._PUBLIC_REASONS | frozenset({
    "authenticated", "authentication_required", "invalid_token", "authentication_error",
    "auth_configuration_unavailable", "batch_authentication_reused", "malformed_json",
    "invalid_request", "request_rejected", "internal_error", "dependency_unavailable",
    "index_unavailable", "preflight_short_circuit", "equipment_unregistered",
    "emergency", "out_of_scope", "conditions_unverified", "law_currentness_unverified",
    "effective_date_missing", "effective_date_invalid", "effective_date_future",
    "law_version_conflict", "msds_applicability_unverified", "precheck_requires_review",
})


def _safe_pipeline_reason(value, fallback: str = "internal_error") -> str:
    return value if isinstance(value, str) and value in _SAFE_PIPELINE_REASONS else fallback


# 기본 접근 로그에는 쿼리 문자열이 포함되므로 아래 미들웨어로 대체한다.
logging.getLogger("uvicorn.access").disabled = True
CORS_OPTIONS = {
    "allow_origins": ["http://localhost:5174", "http://127.0.0.1:5174"],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type"],
    "expose_headers": ["X-Request-ID", *diagnostics.HEADER_NAMES],
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


class _RequestTrace:
    """One request only; worker threads share this collector, never other requests."""

    def __init__(self, started: float, *, parent_request_id: str | None = None) -> None:
        self.request_id = uuid4().hex
        self.started = started
        self.parent_request_id = parent_request_id
        self.events: deque = deque(maxlen=200)
        self.event_count = 0
        self.outcome = "answered"
        self.dispatched = False
        self._lock = Lock()

    def add(self, event: dict, location: dict) -> None:
        # Explicit fields prevent provider payloads, prompts, or credentials from
        # accidentally entering the public diagnostic trace or server logs.
        safe = {key: value for key, value in event.items() if key in {
            "stage", "status", "duration_ms", "reason", "check", "attempt",
            "parent_stage", "hit_count", "exception_type", "http_status", "completed",
            "category", "provider_status", "provider_code", "provider_type",
            "provider_request_id", "retry_after_seconds", "remaining_requests", "remaining_tokens",
        }}
        if "reason" in safe:
            safe["reason"] = _safe_pipeline_reason(safe["reason"])
        with self._lock:
            self.event_count += 1
            safe.update(sequence=self.event_count, elapsed_ms=round((perf_counter() - self.started) * 1000, 3),
                        location=location)
            if safe.get("stage") == "authentication":
                safe.setdefault("parent_stage", "request_dispatch")
            elif safe.get("stage") == "generation_attempt":
                safe.setdefault("parent_stage", "generation")
            elif safe.get("stage") in {"generation_draft", "evidence_validation", "semantic_verification", "review"}:
                safe.setdefault("parent_stage", "generation_attempt" if safe.get("attempt") else "preflight")
            elif safe.get("stage") == "response_mapping":
                safe.setdefault("parent_stage", "generation")
            self.events.append(safe)
        correlation = {"request_id": self.request_id}
        if self.parent_request_id is not None:
            correlation["parent_request_id"] = self.parent_request_id
        trace_log.info("pipeline_event %s", json.dumps({**correlation, **safe}, ensure_ascii=False))

    def envelope(self, status: int, response: dict) -> dict:
        with self._lock:
            events = list(self.events)
            count = self.event_count
        outcome = "error" if status >= 400 else self.outcome
        last_attempt = max((event.get("attempt", 0) for event in events), default=0)
        failures = [event for event in events if event.get("status") in {"held", "error"}
                    and (event.get("reason") or event.get("exception_type"))
                    and event.get("attempt", last_attempt) == last_attempt]
        # Preserve the original failing rule rather than the outer HTTP mapping.
        causes = [event for event in failures if event.get("stage") not in {
            "api_result", "request_dispatch", "generation", "generation_attempt", "evidence_validation",
        }]
        precise = [event for event in causes if event.get("check") or event.get("exception_type")]
        reviews = [event for event in causes if event.get("stage") == "review"]
        failure = dict((precise or reviews or causes or failures)[-1]) if outcome != "answered" and failures else None
        if failure is not None and not failure.get("reason"):
            failure["reason"] = next((event["reason"] for event in reversed(failures) if event.get("reason")), "internal_error")
        return {
            "request_id": self.request_id, "http_status": status, "outcome": outcome,
            "response": response, "failure": failure,
            "timing": {"scope": "response_ready", "total_ms": round((perf_counter() - self.started) * 1000, 3),
                       "note": "부모 단계 시간에는 하위 단계가 포함됩니다. 실제 전송 완료 시간은 서버의 http_complete 로그에 기록됩니다."},
            "trace": events, "trace_truncated": count > len(events),
        }


_active_trace: ContextVar[_RequestTrace | None] = ContextVar("chembridge_request_trace", default=None)


def _source_location(filename: str, function: str, line: int) -> dict:
    try:
        filename = str(Path(filename).resolve().relative_to(Path(__file__).resolve().parents[1]))
    except ValueError:
        filename = "external"
    return {"file": filename, "function": function, "line": line}


class _PipelineHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        trace = _active_trace.get()
        event = getattr(record, "pipeline_event", None)
        if trace is not None and isinstance(event, dict):
            location = getattr(record, "pipeline_location", None)
            trace.add(event, location or _source_location(record.pathname, record.funcName, record.lineno))


pipeline_log.addHandler(_PipelineHandler())
pipeline_log.setLevel(logging.INFO)
pipeline_log.propagate = False


def _pipeline_event(stage: str, status: str, *, error: Exception | None = None, **details) -> None:
    if "reason" in details:
        details["reason"] = _safe_pipeline_reason(details["reason"])
    extra = {"pipeline_event": {"stage": stage, "status": status, **details}}
    if error is not None:
        extra["pipeline_event"]["exception_type"] = type(error).__name__
        tb = error.__traceback__
        while tb is not None:
            location = _source_location(tb.tb_frame.f_code.co_filename, tb.tb_frame.f_code.co_name, tb.tb_lineno)
            if location["file"] != "external":
                extra["pipeline_location"] = location
            tb = tb.tb_next
    pipeline_log.info("pipeline_stage", extra=extra, stacklevel=2)


def _publish_response_diagnostics(details: dict, response: Response, request_id: str) -> dict:
    """Publish only fields produced by rag.diagnostics, never raw exceptions."""
    details = dict(details)
    if "reason" in details:
        details["reason"] = _safe_pipeline_reason(details["reason"])
    headers = diagnostics.response_headers(details, request_id)
    response.headers.update(headers)
    category = details.get("category")
    status = "ok" if category == "answer" else "error" if category in {
        "provider_error", "experiment_stopped", "generation_error", "verifier_unavailable",
    } else "held"
    stage = details.pop("stage", "api_result")
    _pipeline_event(stage, status, **details)
    return headers


@app.exception_handler(RequestValidationError)
async def _request_validation_error(request: Request, exc: RequestValidationError):
    reason = "malformed_json" if any(error["type"] == "json_invalid" for error in exc.errors()) else "invalid_request"
    _pipeline_event("request_validation", "error", reason=reason, parent_stage="request_dispatch")
    return await request_validation_exception_handler(request, exc)


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
    """HTTP 완료 기록과 요청별 파이프라인 수집. 진단 POST에만 로그 봉투를 붙인다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        trace = _RequestTrace(started) if scope["path"] in {"/rag-query", DIAGNOSTIC_PATH, EVALUATION_PATH} else None
        trace_token = _active_trace.set(trace)
        diagnostic = trace is not None and scope["path"] == DIAGNOSTIC_PATH and scope["method"] == "POST"
        pending_start: Message | None = None
        response_parts: list[bytes] = []
        status_code = 500
        response_started = False
        response_completed = False
        finished: float | None = None

        async def capture_status(message: Message) -> None:
            nonlocal status_code, response_started, response_completed, finished, pending_start
            if message["type"] == "http.response.start":
                status_code = message["status"]
                if trace is not None:
                    message = {**message, "headers": [*message.get("headers", []),
                                                       (b"x-request-id", trace.request_id.encode("ascii"))]}
                if diagnostic:
                    pending_start = message
                    response_parts.clear()
                    return
                response_started = True
            if diagnostic and message["type"] == "http.response.body":
                response_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                payload = json.loads(b"".join(response_parts))
                if not trace.dispatched:
                    _pipeline_event("request_dispatch", "error", duration_ms=(perf_counter() - started) * 1000,
                                    reason="request_rejected")
                    trace.dispatched = True
                _pipeline_event("response_ready", "ok")
                wrapped = JSONResponse(trace.envelope(status_code, payload)).body
                headers = [(key, value) for key, value in pending_start.get("headers", [])
                           if key.lower() not in {b"content-length", b"cache-control"}]
                await send({**pending_start, "headers": [*headers, (b"content-length", str(len(wrapped)).encode("ascii")),
                                                         (b"cache-control", b"no-store")]})
                response_started = True
                await send({**message, "body": wrapped})
                response_completed = True
                finished = perf_counter()
                return
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_completed = True
                finished = perf_counter()

        try:
            await self.app(scope, receive, capture_status)
        except Exception as exc:
            _pipeline_event("api_result", "error", error=exc, reason="internal_error")
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
            try:
                # 등록되지 않은 경로의 사용자 입력도 로그에 남기지 않는다.
                path = getattr(scope.get("route"), "path", "/unmatched")
                # CORS preflight는 라우터 전에 끝나므로 등록된 경로만 별도로 확인한다.
                if path == "/unmatched" and scope["path"] in {route.path for route in app.routes}:
                    path = scope["path"]
                elapsed_ms = ((finished if finished is not None else perf_counter()) - started) * 1000
                request_log.info(
                    "path=%s status=%d latency_ms=%.2f request_id=%s",
                    path, status_code, elapsed_ms, trace.request_id if trace is not None else "-",
                )
                if trace is not None:
                    _pipeline_event("http_complete", "ok" if response_completed else "error", duration_ms=elapsed_ms,
                                    http_status=status_code, completed=response_completed)
                # 대시보드 조회 자체는 집계에서 제외한다.
                if not (path == "/raq-query-log" and scope["method"] == "GET"):
                    latency_stats.record(path, scope["method"], status_code, elapsed_ms, response_completed)
            finally:
                _active_trace.reset(trace_token)


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
            "description": "모든 필수 topic 인덱스가 준비됨. 각 topic의 상태는 indexes에서 확인합니다.",
            "content": {"application/json": {"example": {
                "ready": True,
                "indexes": {TOPIC_LAW: True, TOPIC_CHEMICAL: True},
            }}},
        },
        503: {
            "description": "필수 인덱스 중 하나 이상이 준비되지 않음.",
            "content": {"application/json": {"example": {
                "ready": False,
                "indexes": {TOPIC_LAW: False, TOPIC_CHEMICAL: False},
            }}},
        },
    },
)
def health():
    """인증 없이 호출합니다. 전체 준비 상태와 topic별 인덱스 상태를 반환합니다."""
    indexes = stores.status()
    body = {"ready": bool(indexes) and all(indexes.values()), "indexes": indexes}
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
            "description": "인증 설정·요청 topic 인덱스 미준비 또는 검색·생성·검증 서비스 장애. 근거 부족·안전 검증 보류는 200입니다.",
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
    정상 보류는 200, 알려진 서비스 장애는 503, 예상하지 못한 내부 오류는 500입니다.
    """
    trace = _active_trace.get()
    if trace is not None:
        _pipeline_event("request_dispatch", "ok", duration_ms=(perf_counter() - trace.started) * 1000)
        trace.dispatched = True
    request_id = trace.request_id if trace is not None else uuid4().hex
    with diagnostics.capture_failures() as failures:
        try:
            result = answer(req)
            if trace is not None:
                trace.outcome = "held" if result.handoff else "answered"
            details = diagnostics.result_details(result)
            if result.handoff and failures and failures[-1].get("category") in {"provider_error", "experiment_stopped"}:
                details = failures[-1]
            _publish_response_diagnostics(details, response, request_id)
            return result
        except (GenerationUnavailable, RAGUnavailable, diagnostics.ExperimentStopped,
                TimeoutError, ConnectionError, OSError, httpx.HTTPError, APIError) as exc:
            reason = _safe_pipeline_reason(getattr(exc, "reason", None), "dependency_unavailable")
            _pipeline_event("api_result", "error", error=exc, reason=reason)
            details = failures[-1] if failures else diagnostics.exception_details(exc, stage="chain")
            headers = _publish_response_diagnostics(details, response, request_id)
            raise HTTPException(status_code=503, detail="잠시 후 다시 시도해 주세요.", headers=headers) from None
        except Exception as exc:
            _pipeline_event("api_result", "error", error=exc, reason="internal_error")
            headers = _publish_response_diagnostics(diagnostics.exception_details(exc, stage="chain"), response, request_id)
            raise HTTPException(status_code=500, detail="요청 처리 중 오류가 발생했습니다.", headers=headers) from None


class _DiagnosticResponse(BaseModel):
    request_id: str
    http_status: int
    outcome: str
    response: RagResponse | dict
    failure: dict | None
    timing: dict
    trace: list[dict]
    trace_truncated: bool


@app.post(
    DIAGNOSTIC_PATH,
    tags=["서비스 상태"],
    response_model=None,
    summary="한 요청의 RAG 응답과 파이프라인 진단",
    description=(
        "POST /rag-query와 같은 요청·인증으로 chain.answer를 정확히 한 번 실행합니다. "
        "응답은 request_id, http_status, outcome, response(기존 응답), failure, timing, trace를 포함합니다. "
        "인증·요청 검증 실패도 실제 401/422/503 상태와 진단 봉투로 반환합니다. "
        "trace에는 단계·시도별 시간, 보류/오류 사유, 검사명, 코드 위치, 검색 건수가 포함됩니다. "
        "request_dispatch는 JSON 파싱·인증·요청 검증을 포함한 전체 진입 구간이며, "
        "generation은 생성 시도·원문 검증·의미 검증을 포함합니다. 부모·자식 시간을 합산하지 마세요. "
        "본문 시간은 response_ready까지이며 전송 완료 시간은 같은 request_id의 서버 http_complete 로그에 남습니다. "
        "trace에는 질문·답변·프롬프트·토큰·쿠키·예외 원문을 기록하지 않습니다. "
        "실제 답변은 response에만 있으며 다른 사용자의 요청 기록은 조회하지 않습니다."
    ),
    responses={
        code: {"model": _DiagnosticResponse, "description": description}
        for code, description in {
            200: "답변 완료 또는 안전상 보류. outcome과 failure를 확인하세요.",
            401: "토큰 없음·만료·위조.", 422: "JSON 또는 요청 필드 검증 실패.",
            503: "인증·인덱스 미준비 또는 검색·생성·검증 서비스 장애.",
            500: "예상하지 못한 내부 오류.",
        }.items()
    },
)
def rag_query_diagnostics(req: RagRequest, response: Response, user: dict = Depends(get_current_user)) -> RagResponse:
    # The middleware also wraps failures that happen before this function runs.
    return rag_query(req, response=response, user=user)


class _EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _EvaluationRequest(_EvaluationModel):
    dataset_path: str = Field(min_length=1, max_length=1024,
                              description="서버의 rag-service/eval 안에 있는 JSON 경로. 예: eval/diagnostic_cases_40.json",
                              examples=["eval/diagnostic_cases_40.json"])


class _EvaluationExpected(_EvaluationModel):
    http_status: int = Field(ge=100, le=599)
    outcome: Literal["answered", "held", "error"]
    handoff: bool | None = None
    needs_review: bool | None = None
    sources_min: int = Field(default=0, ge=0)
    sources_max: int | None = Field(default=None, ge=0)
    source_doc_ids_any: list[str] = Field(default_factory=list)
    reason_any: list[str] = Field(default_factory=list)
    answer_contains: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_bounds(self):
        if self.sources_max is not None and self.sources_max < self.sources_min:
            raise ValueError("sources_max must be at least sources_min")
        return self


class _EvaluationCase(_EvaluationModel):
    id: str = Field(min_length=1, max_length=100)
    split: Literal["test", "validation"]
    category: str = ""
    # Keep raw input so a dataset can deliberately test 422 responses too.
    request: dict
    expected: _EvaluationExpected
    notes: str = ""


class _EvaluationDataset(_EvaluationModel):
    version: Literal[1]
    name: str
    description: str = ""
    cases: list[_EvaluationCase] = Field(min_length=1, max_length=100)


def _load_evaluation_dataset(dataset_path: str) -> tuple[_EvaluationDataset, str]:
    try:
        root = _EVALUATION_ROOT.resolve()
        supplied = Path(dataset_path)
        if supplied.is_absolute():
            path = supplied.resolve()
        elif supplied.parts[:2] == ("rag-service", "eval"):
            path = root.joinpath(*supplied.parts[2:]).resolve()
        elif supplied.parts[:1] == ("eval",):
            path = root.joinpath(*supplied.parts[1:]).resolve()
        else:
            path = (root / supplied).resolve()
    except (ValueError, RuntimeError):
        raise HTTPException(422, "평가셋 경로 형식이 올바르지 않습니다.") from None
    except OSError:
        raise HTTPException(503, "평가셋 경로를 확인할 수 없습니다.") from None
    if not path.is_relative_to(root) or path.suffix.lower() != ".json":
        raise HTTPException(422, "rag-service/eval 안의 JSON 평가셋 경로를 입력하세요.")
    try:
        with path.open("rb") as source:
            content = source.read(1_048_577)
    except FileNotFoundError:
        raise HTTPException(404, "평가셋 파일을 찾을 수 없습니다.") from None
    except IsADirectoryError:
        raise HTTPException(422, "JSON 파일 경로를 입력하세요.") from None
    except OSError:
        raise HTTPException(503, "평가셋 파일을 읽을 수 없습니다.") from None
    if len(content) > 1_048_576:
        raise HTTPException(422, "평가셋은 1 MiB 이하로 입력하세요.")
    try:
        decoded = json.loads(content.decode("utf-8"))
        # Validate round-trip JSON before any model calls. Raw case inputs may
        # deliberately be invalid RagRequests, but must still be valid UTF-8 JSON.
        json.dumps(decoded, ensure_ascii=False, allow_nan=False).encode("utf-8")
        dataset = _EvaluationDataset.model_validate(decoded)
    except (UnicodeError, ValueError, RecursionError):
        raise HTTPException(422, "평가셋 JSON 형식 또는 케이스·기대값 구성이 올바르지 않습니다.") from None
    if len({case.id for case in dataset.cases}) != len(dataset.cases):
        raise HTTPException(422, "평가 케이스 ID는 중복될 수 없습니다.")
    return dataset, "eval/" + path.relative_to(root).as_posix()


def _run_evaluation_case(case: _EvaluationCase, user: dict, run_id: str) -> dict:
    trace = _RequestTrace(perf_counter(), parent_request_id=run_id)
    token = _active_trace.set(trace)
    try:
        _pipeline_event("authentication", "skipped", duration_ms=0.0, reason="batch_authentication_reused")
        try:
            request = RagRequest.model_validate(case.request)
        except ValidationError as exc:
            status = 422
            payload = {"detail": exc.errors(include_url=False, include_context=False, include_input=False)}
            _pipeline_event("request_validation", "error", reason="invalid_request", parent_stage="request_dispatch")
            _pipeline_event("request_dispatch", "error", duration_ms=(perf_counter() - trace.started) * 1000,
                            reason="request_rejected")
        else:
            try:
                response = rag_query(request, response=Response(), user=user)
                payload = response.model_dump(mode="json")
                json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                status = 200
            except HTTPException as exc:
                payload, status = {"detail": exc.detail}, exc.status_code
            except Exception as exc:
                _pipeline_event("api_result", "error", error=exc, reason="internal_error")
                payload, status = {"detail": "요청 처리 중 오류가 발생했습니다."}, 500
        _pipeline_event("response_ready", "ok")
        diagnostic = trace.envelope(status, payload)
        diagnostic["timing"]["note"] = (
            "배치 내부 케이스의 response_ready까지 측정합니다. "
            "실제 HTTP 전송 완료 시간은 상위 run_id의 http_complete 로그를 확인하세요."
        )
        # Cases are in-process executions, not individual HTTP exchanges.
        _pipeline_event("case_complete", "ok", duration_ms=(perf_counter() - trace.started) * 1000,
                        http_status=status, completed=True)
        return diagnostic
    finally:
        _active_trace.reset(token)


def _grade_evaluation(expected: _EvaluationExpected, diagnostic: dict) -> list[dict]:
    checks = []

    def check(name, wanted, actual, passed):
        checks.append({"name": name, "expected": wanted, "actual": actual, "passed": bool(passed)})

    check("http_status", expected.http_status, diagnostic["http_status"], expected.http_status == diagnostic["http_status"])
    check("outcome", expected.outcome, diagnostic["outcome"], expected.outcome == diagnostic["outcome"])
    response = RagResponse.model_validate(diagnostic["response"]) if diagnostic["http_status"] == 200 else None
    for field_name in ("handoff", "needs_review"):
        wanted = getattr(expected, field_name)
        if wanted is not None:
            actual = getattr(response, field_name) if response is not None else None
            check(field_name, wanted, actual, wanted == actual)
    sources = response.sources if response is not None else []
    check("sources_min", expected.sources_min, len(sources), len(sources) >= expected.sources_min)
    if expected.sources_max is not None:
        check("sources_max", expected.sources_max, len(sources), len(sources) <= expected.sources_max)
    if expected.source_doc_ids_any:
        actual = sorted({source.doc_id for source in sources})
        check("source_doc_ids_any", expected.source_doc_ids_any, actual, bool(set(actual) & set(expected.source_doc_ids_any)))
    if expected.reason_any:
        actual = (diagnostic["failure"] or {}).get("reason")
        check("reason_any", expected.reason_any, actual, actual in expected.reason_any)
    if expected.answer_contains:
        missing = [fragment for fragment in expected.answer_contains if response is None or fragment not in response.answer]
        check("answer_contains", expected.answer_contains, {"missing": missing}, not missing)
    return checks


class _EvaluationResponse(BaseModel):
    run_id: str
    dataset_path: str
    total_cases: int
    summary: dict
    results: list[dict]


@app.post(
    EVALUATION_PATH,
    tags=["서비스 상태"],
    summary="JSON 평가셋 전체 실행 · 케이스별 진단 로그와 기대값 비교",
    response_model=None,
    description=(
        "dataset_path만 입력하면 서버 rag-service/eval 안의 JSON을 읽어 최대 100개 케이스를 순서대로 실행합니다. "
        "예: {\"dataset_path\":\"eval/diagnostic_cases_40.json\"}. "
        "각 results 항목은 /rag-query/diagnostics와 같은 진단 필드 및 case_id, request, expected, checks, passed를 가집니다. "
        "인증은 배치 요청에서 한 번 수행하고 케이스별 trace에 재사용을 표시합니다. "
        "한 케이스의 422/500/503도 결과에 남기고 나머지를 계속 실행합니다. "
        "배치 완료의 HTTP 200과 개별 케이스의 http_status·passed는 별개입니다. "
        "summary.error_count는 예상된 422를 포함해 outcome=error인 케이스 수입니다. "
        "실제 LLM을 호출하므로 전체 실행에는 수 분과 API 사용료가 발생할 수 있습니다. "
        "평가는 기대 동작·출처·사유·지정 문구를 비교하며 답변 내용 전체의 사실성을 자동 판정하지 않습니다."
    ),
    responses={
        200: {"model": _EvaluationResponse, "description": "배치 실행 완료. summary와 케이스별 passed·http_status를 확인하세요."},
        401: {"description": "인증 실패."}, 404: {"description": "평가셋 파일 없음."},
        422: {"description": "경로·파일 크기·JSON·평가셋 구성 오류. 실행 전에 검사합니다."},
        503: {"description": "인증 설정 또는 평가셋 읽기 장애."},
    },
)
def rag_evaluations(req: _EvaluationRequest, user: dict = Depends(get_current_user)) -> JSONResponse:
    started = perf_counter()
    dataset, path = _load_evaluation_dataset(req.dataset_path)
    parent = _active_trace.get()
    run_id = parent.request_id if parent is not None else uuid4().hex
    results = []
    for case in dataset.cases:
        diagnostic = _run_evaluation_case(case, user, run_id)
        checks = _grade_evaluation(case.expected, diagnostic)
        results.append({"case_id": case.id, "split": case.split, "category": case.category,
                        "request": case.request, "expected": case.expected.model_dump(exclude_none=True),
                        "checks": checks, "passed": all(check["passed"] for check in checks), **diagnostic})
    total = len(results)
    passed = sum(row["passed"] for row in results)
    by_split = {}
    for split in ("test", "validation"):
        rows = [row for row in results if row["split"] == split]
        good = sum(row["passed"] for row in rows)
        by_split[split] = {"total": len(rows), "passed": good, "failed": len(rows) - good,
                           "pass_rate": round(good / len(rows), 6) if rows else 0.0}
    summary = {"passed": passed, "failed": total - passed, "pass_rate": round(passed / total, 6),
               "error_count": sum(row["outcome"] == "error" for row in results), "by_split": by_split,
               "status_counts": dict(Counter(str(row["http_status"]) for row in results)),
               "duration_ms": round((perf_counter() - started) * 1000, 3)}
    return JSONResponse({"run_id": run_id, "dataset_path": path, "total_cases": total,
                         "summary": summary, "results": results}, headers={"Cache-Control": "no-store"})


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
