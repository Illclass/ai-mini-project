"""평가 — 담당: 김규빈 (검색 지표) · 박진근 (생성 지표)

questions.json 항목:
    id, question, language, topic, product_id,
    expected_answer, expected_sources [{doc_id, section}],
    expected_behavior: "answer" | "not_found" | "handoff"

실행 (rag-service/ 에서): python -m eval.run_eval
"""
from typing import List


def load_questions(path: str = "eval/questions.json") -> List[dict]:
    """평가셋 로드."""
    # TODO
    raise NotImplementedError


def hit_at_k(hits: List[dict], expected_sources: List[dict]) -> bool:
    """검색 적중: 기대 근거(doc_id + section)가 hits 의 metadata 안에 있는가."""
    # TODO
    raise NotImplementedError


def judge_behavior(response: dict, expected_behavior: str) -> bool:
    """생성 판정: handoff · "찾을 수 없음" 이 기대와 맞는가."""
    # TODO
    raise NotImplementedError


def main() -> None:
    """질문마다 retrieve → hit_at_k, chain.answer → judge_behavior. 결과표(적중률·정확도·응답시간) 출력."""
    # TODO
    raise NotImplementedError


if __name__ == "__main__":
    main()
