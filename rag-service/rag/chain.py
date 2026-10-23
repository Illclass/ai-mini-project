"""검색 → 생성 연결 — 담당: 김규빈 · 박진근 (공동)

API 가 부르는 유일한 함수는 answer(req) 하나다.
비상·범위 밖 질문은 생성 담당의 preflight_result 가 검색·LLM 보다 먼저 처리한다
(비상 안내 문구·판정 규칙은 rag/generator.py · rag/prompt.py 의 TEXT 한 곳에서만 관리).
"""
import time

from rag import equipment
from rag.generator import generate, preflight_result
from rag.retriever import retrieve
from rag.schema import RagRequest, RagResponse


def answer(req: RagRequest) -> RagResponse:
    """흐름: preflight(비상·범위 밖) → retriever.retrieve(제품·장비 범위) → generator.generate → 미등록 장비 → latency_ms."""
    t0 = time.perf_counter()

    early = preflight_result(req.question, req.language)
    if early is not None:   # 검색·LLM 을 기다리지 않고 비상 안내 / 범위 밖 안내
        resp = RagResponse(**early.model_dump())
    else:
        hits = retrieve(req.question, req.topic, req.product_id, language=req.language,
                        equipment_id=req.equipment_id)
        resp = generate(req.question, hits, req.language, product_id=req.product_id, topic=req.topic)
        if equipment.is_unregistered(req.equipment_id):   # 사용 물질 MSDS 가 없는 장비 → 담당자 확인
            resp.needs_review = True
            resp.handoff = True

    resp.latency_ms = int((time.perf_counter() - t0) * 1000)
    return resp
