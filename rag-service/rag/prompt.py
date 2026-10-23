"""프롬프트 — 담당: 박진근

규칙(기획서): 검색된 근거만 사용, 없으면 "찾을 수 없음", 개별 법률 판단·책임 단정 금지,
답변 언어 = 요청 language, 끝에 "참고용, 현장 MSDS·담당자 확인" 문구.
(지금은 틀이 동작하도록 넣은 임시 버전 — 다듬기는 생성 담당)
"""
from typing import Dict, List

from rag.schema import Hit

LANGUAGE_NAMES = {"ko": "한국어", "zh": "중국어(간체)", "vi": "베트남어", "en": "영어", "km": "크메르어(캄보디아어)"}

SYSTEM_PROMPT = (
    "당신은 반도체 공정 근로자를 위한 화학안전·중대재해 법령 안내 도우미입니다.\n"
    "- 아래 [근거] 안의 내용만 사용해 답하고, 근거에 없는 내용은 지어내지 마세요.\n"
    "- 근거가 질문과 관련 있으면 근거에 적힌 범위에서 답하고, 근거로 확인되지 않는 부분은 그렇다고 밝히세요.\n"
    "- 근거가 질문과 전혀 관련 없을 때만 '제공된 자료에서 찾을 수 없습니다'라고 답하세요.\n"
    "- 답에 쓴 조문 번호(예: 제6조)를 함께 적으세요.\n"
    "- 특정 회사·사고의 법적 책임이나 처벌 여부를 단정하지 마세요.\n"
    "- 쉬운 문장으로 짧게 답하세요."
)


def build_messages(question: str, hits: List[Hit], language: str) -> List[Dict[str, str]]:
    """LLM 에 보낼 messages ([{"role": ..., "content": ...}])."""
    context = "\n\n".join(f"[근거 {i}]\n{h['text']}" for i, h in enumerate(hits, start=1))
    lang = LANGUAGE_NAMES.get(language, "한국어")
    user = f"{context}\n\n질문: {question}\n\n{lang}로 답하세요."
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
