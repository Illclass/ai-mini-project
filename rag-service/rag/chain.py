"""검색 → 생성 연결 — 담당: 김규빈 · 박진근 (공동)

API 가 부르는 유일한 함수는 answer(req) 하나다.
"""
import time

from rag.generator import generate
from rag.retriever import retrieve
from rag.schema import RagRequest, RagResponse

# 노출·사고 상황 표현 (TODO: zh · vi 표현 추가)
EMERGENCY_WORDS = ("눈에 들어", "피부에 닿", "피부에 묻", "흡입", "삼켰", "마셨", "쓰러", "화상", "누출", "새고 있")

EMERGENCY_NOTICE = {
    "ko": "⚠ 긴급 상황이면 즉시 작업을 멈추고 119와 현장 안전관리자에게 연락하세요. 아래는 참고 정보입니다.\n\n",
    "zh": "⚠ 如属紧急情况，请立即停止作业，并联系119和现场安全管理人员。以下为参考信息。\n\n",
    "vi": "⚠ Nếu khẩn cấp, hãy dừng công việc ngay và gọi 119 cùng người quản lý an toàn tại hiện trường. Dưới đây là thông tin tham khảo.\n\n",
}


def is_emergency(question: str) -> bool:
    """노출·사고 상황 질문인가 ("눈에 들어갔어요", "흡입했어요" 등). True 면 비상 안내 우선 + handoff."""
    return any(w in question for w in EMERGENCY_WORDS)


def answer(req: RagRequest) -> RagResponse:
    """흐름: is_emergency → query.normalize_question → retriever.retrieve → generator.generate → latency_ms."""
    t0 = time.perf_counter()

    emergency = is_emergency(req.question)
    hits = retrieve(req.question, req.topic, req.product_id, language=req.language)
    resp = generate(req.question, hits, req.language)

    if emergency:
        resp.answer = EMERGENCY_NOTICE.get(req.language, EMERGENCY_NOTICE["ko"]) + resp.answer
        resp.handoff = True

    resp.latency_ms = int((time.perf_counter() - t0) * 1000)
    return resp
