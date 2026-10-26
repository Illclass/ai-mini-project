"""검색 → 생성 연결 — 담당: 김규빈 · 박진근 (공동)

API 가 부르는 유일한 함수는 answer(req) 하나다.
비상·범위 밖 질문은 생성 담당의 preflight_result 가 검색·LLM 보다 먼저 처리한다
(비상 안내 문구·판정 규칙은 rag/generator.py · rag/prompt.py 의 TEXT 한 곳에서만 관리).
"""
import logging
import time

from rag import equipment, stores
from rag.generator import generate, preflight_result
from rag.products import resolve_product_id
from rag.query import question_language
from rag.retriever import retrieve
from rag.schema import RagRequest, RagResponse


logger = logging.getLogger("chembridge.pipeline")


class RAGUnavailable(RuntimeError):
    """The requested retrieval index is not ready; no request data is exposed."""

    reason = "index_unavailable"


def _record_stage(stage: str, status: str, started: float | None, **details) -> None:
    logger.info(
        "pipeline_stage",
        extra={"pipeline_event": {
            "stage": stage,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3) if started is not None else 0.0,
            **details,
        }},
        stacklevel=2,
    )


def answer(req: RagRequest) -> RagResponse:
    """흐름: preflight(비상·범위 밖) → 제품 자동 지정 → retriever.retrieve(제품·장비 범위) → generator.generate
    → 미등록 장비 → latency_ms."""
    t0 = time.perf_counter()
    # 화면 언어와 다른 말로 물으면 질문한 말로 답한다 (예: 한국어 화면에서 영어 질문)
    req = req.model_copy(update={"language": question_language(req.question, req.language)})

    started = time.perf_counter()
    try:
        early = preflight_result(req.question, req.language)
    except Exception as exc:
        _record_stage("preflight", "error", started, exception_type=type(exc).__name__)
        raise
    _record_stage("preflight", "held" if early is not None else "ok", started)
    if early is not None:   # 검색·LLM 을 기다리지 않고 비상 안내 / 범위 밖 안내
        for stage in ("product_resolution", "retrieval", "generation", "equipment_review"):
            _record_stage(stage, "skipped", None, reason="preflight_short_circuit")
    else:
        # 물질명으로 제품을 정해 검색 범위와 생성 쪽 제품 확인에 같은 값을 쓴다 (못 정하면 요청 값 그대로)
        started = time.perf_counter()
        try:
            product_id = resolve_product_id(req.question, req.topic, req.language, req.product_id, req.equipment_id)
        except Exception as exc:
            _record_stage("product_resolution", "error", started, exception_type=type(exc).__name__)
            raise
        _record_stage("product_resolution", "ok", started)

        started = time.perf_counter()
        try:
            if stores.get_store(req.topic) is None:
                raise RAGUnavailable("The requested retrieval index is not ready")
            hits = retrieve(req.question, req.topic, product_id, language=req.language,
                            equipment_id=req.equipment_id)
        except Exception as exc:
            details = {"exception_type": type(exc).__name__}
            if isinstance(exc, RAGUnavailable):
                details["reason"] = exc.reason
            _record_stage("retrieval", "error", started, **details)
            raise
        _record_stage("retrieval", "ok", started, hit_count=len(hits))

        started = time.perf_counter()
        try:
            resp = generate(req.question, hits, req.language, product_id=product_id, topic=req.topic)
        except Exception as exc:
            _record_stage("generation", "error", started, exception_type=type(exc).__name__)
            raise
        _record_stage("generation", "held" if resp.handoff else "ok", started)

        started = time.perf_counter()
        try:
            unregistered = equipment.is_unregistered(req.equipment_id)
            if unregistered:   # 사용 물질 MSDS 가 없는 장비 → 담당자 확인
                resp.needs_review = True
                resp.handoff = True
        except Exception as exc:
            _record_stage("equipment_review", "error", started, exception_type=type(exc).__name__)
            raise
        _record_stage("equipment_review", "held" if unregistered else "ok", started,
                      **({"reason": "equipment_unregistered"} if unregistered else {}))

    started = time.perf_counter()
    try:
        if early is not None:
            resp = RagResponse(**early.model_dump())
        resp.latency_ms = int((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        _record_stage("response_finalization", "error", started, exception_type=type(exc).__name__)
        raise
    _record_stage("response_finalization", "ok", started)
    return resp
