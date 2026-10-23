"""ChemBridge 공통 이름 규칙 — 팀 전원이 이 파일의 이름만 사용한다.

바꾸고 싶은 이름이 있으면 이 파일을 먼저 고치고 팀에 공유한다.

    파트            주로 쓰는 것
    데이터(윤서진)   ChunkMeta 키, DOC_TYPE_*, TOPIC_*, INDEX_DIRS, make_chunk_id()
    검색(김규빈)     retrieve() 시그니처, Hit
    생성(박진근)     generate() 시그니처, Source, RagResponse
    API(정지우)      RagRequest, RagResponse, ENV_*
    프론트(강지훈)   RagRequest / RagResponse 의 JSON 필드명, LANGUAGES, TOPICS
"""
from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. 고정 값 (enum)
# ---------------------------------------------------------------------------
TOPIC_CHEMICAL = "chemical_safety"        # 화학물질 안전 (MSDS)
TOPIC_LAW = "serious_accident_law"        # 중대재해·산업안전 법령
TOPICS = (TOPIC_CHEMICAL, TOPIC_LAW)
Topic = Literal["chemical_safety", "serious_accident_law"]

LANGUAGES = ("ko", "zh", "vi", "en", "km")   # 한국어 · 중국어 · 베트남어 · 영어 · 크메르어(캄보디아)
Language = Literal["ko", "zh", "vi", "en", "km"]

DOC_TYPE_LAW = "law"                      # 법령 원문 (조문 단위 청크)
DOC_TYPE_MSDS = "msds"                    # 제품 MSDS (16개 항목 단위 청크)
DOC_TYPE_GUIDE = "guide"                  # KOSHA GUIDE 등 지침
DOC_TYPE_WEB = "web"                      # 웹 수집
DocType = Literal["law", "msds", "guide", "web"]

# topic 별 FAISS 인덱스 경로 (rag-service/ 기준)
INDEX_DIRS: Dict[str, str] = {
    TOPIC_LAW: "faiss_db/law",
    TOPIC_CHEMICAL: "faiss_db/msds",
}

# ---------------------------------------------------------------------------
# 2. 환경변수 이름 (값은 각자 .env 에)
# ---------------------------------------------------------------------------
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_JWT_SECRET = "JWT_SECRET"             # Java 인증서버와 같은 값
ENV_LLM_MODEL = "LLM_MODEL"               # 예: gpt-4o
ENV_EMBEDDING_MODEL = "EMBEDDING_MODEL"   # 비우면 DEFAULT_EMBEDDING_MODEL (rag/embeddings.py 참고)
ENV_TOP_K = "RAG_TOP_K"                   # 기본 5

DEFAULT_TOP_K = 5
DEFAULT_EMBEDDING_MODEL = "bge-m3"   # 로컬 다국어 모델. 근거: eval/results/20261023_1139_retrieval.md (hit@5 98%)

# ---------------------------------------------------------------------------
# 3. 청크 메타데이터 (적재 → 검색 → 출처 표시)
# ---------------------------------------------------------------------------
class ChunkMeta(TypedDict, total=False):
    # 공통 — 모든 청크 필수
    doc_id: str           # 기획서 문서 ID: "L1", "L2", "D1" ...
    doc_type: str         # DOC_TYPE_*
    topic: str            # TOPIC_*
    title: str            # 화면에 보일 문서명: "중대재해 처벌 등에 관한 법률", "Sulfuric acid 339741 MSDS"
    section: str          # 화면에 보일 위치: "제2조 제2호", "8. 노출방지 및 개인보호구"
    source_url: str       # 원문 링크
    chunk_id: str         # make_chunk_id() 로 생성, 전체에서 유일
    effective_date: str   # 법령 시행일 / MSDS 개정일 (YYYY-MM-DD)

    # 법령 전용 (doc_type == "law")
    law_name: str         # "중대재해 처벌 등에 관한 법률"
    article_no: str       # "제2조", "제5조의2"
    article_title: str    # "정의"
    paragraph: str        # 항 번호 "1" … (항 단위로 쪼갰을 때만, 아니면 "")

    # MSDS 전용 (doc_type == "msds")
    product_id: str       # "{공급자}-{제품번호}" 예: "sigma-339741"
    substance: str        # 물질명(한글): "황산"
    cas_no: str           # "7664-93-9"
    supplier: str         # "Sigma-Aldrich Korea"
    msds_section_no: int  # 1 ~ 16


def make_chunk_id(doc_id: str, part: str) -> str:
    """chunk_id 규칙: "{doc_id}-{part}".  예) L2-2-2 (제2조 2항), D1-s8 (MSDS 8항)"""
    return f"{doc_id}-{part}"


# ---------------------------------------------------------------------------
# 4. 검색 결과 (검색 → 생성)
# ---------------------------------------------------------------------------
class Hit(TypedDict):
    text: str             # 청크 본문
    score: float          # FAISS L2 거리 (작을수록 가깝다)
    metadata: ChunkMeta


# retrieve(question: str, topic: Topic, product_id: Optional[str] = None,
#          k: int = DEFAULT_TOP_K) -> List[Hit]
#   - question 은 검색용 한국어 (다국어 → 한국어 변환은 검색 쪽에서 처리)
#   - topic 의 인덱스만 검색, product_id 가 있으면 그 제품 MSDS 만
#   - equipment_id 는 장비에 연결된 제품 목록으로 바꿔 검색 범위를 정한다 (rag/equipment.py)
#   - 결과 없으면 [] → 생성 쪽은 LLM 을 부르지 않는다
#
# generate(question: str, hits: List[Hit], language: Language) -> RagResponse
#   - hits 만 근거로 답하고, sources 는 hits 의 metadata 로 채운다

# ---------------------------------------------------------------------------
# 5. API 요청·응답 (프론트 ↔ API ↔ RAG)  — 기획서 5장 계약
# ---------------------------------------------------------------------------
class RagRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    topic: Topic
    product_id: Optional[str] = None      # 법령 질문은 null
    equipment_id: Optional[str] = None    # 가상 장비 ID 예) "DEMO-WET-01" (data/equipment_map.json)
    language: Language = "ko"


class Source(BaseModel):
    doc_id: str
    section: str
    title: str
    url: str = ""


class RagResponse(BaseModel):
    answer: str
    sources: List[Source] = []
    needs_review: bool = False            # 근거 부족·수치 포함 등 담당자 확인 필요
    handoff: bool = False                 # 개별 법률 판단·사고/노출 상황 → 담당자 연결
    latency_ms: int = 0


def source_from_meta(meta: ChunkMeta) -> Source:
    """검색 결과 메타데이터 → 응답 sources 항목.
    공통 키(title·section)가 없으면 법령 전용 키(law_name·article_no·paragraph)로 채운다."""
    section = meta.get("section") or meta.get("article_no", "")
    if not meta.get("section") and meta.get("paragraph"):
        section = f"{section} 제{meta['paragraph']}항"
    return Source(
        doc_id=meta.get("doc_id", ""),
        section=section,
        title=meta.get("title") or meta.get("law_name", ""),
        url=meta.get("source_url", ""),
    )
