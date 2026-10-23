"""질문 속 물질명 → 제품(product_id) 자동 지정 — 담당: 김규빈

생성 쪽은 MSDS 로 답할 때 product_id 가 반드시 있어야 한다 (다른 제품 정보로 답하지 않기 위해).
작업자는 "불산 보호구는?"처럼 물질명만 말하므로, 물질 하나에 MSDS 가 하나뿐이면 그 제품으로 정한다.
    - 물질명이 없거나 두 개 이상이면 정하지 않는다 (생성 쪽이 "제품 확인 필요"로 안내).
    - 장비를 골랐으면 그 장비의 제품 안에서만 고른다.
    - 같은 물질의 MSDS 가 여러 개(농도·공급사별)가 되면 자동 지정하지 않는다.
"""
import re
from functools import lru_cache
from typing import Dict, List, Optional, Set

from rag import equipment
from rag.query import to_korean
from rag.schema import DOC_TYPE_MSDS, TOPIC_CHEMICAL
from rag.stores import get_store

# MSDS 메타데이터의 substance → 질문에 나올 수 있는 이름 (한국어 · 영어 · 중국어 · 화학식)
# vi · km 질문은 한국어로 번역한 뒤 찾는다.
ALIASES: Dict[str, List[str]] = {
    "황산": ["황산", "sulfuric acid", "sulphuric acid", "H2SO4", "硫酸"],
    "불산": ["불산", "불화수소", "hydrofluoric", "HF", "氢氟酸"],
    "과산화수소": ["과산화수소", "과수", "hydrogen peroxide", "H2O2", "过氧化氢", "双氧水"],
    "암모니아수": ["암모니아", "ammonium hydroxide", "ammonia", "氨水"],
    "염산": ["염산", "염화수소", "hydrochloric", "HCl", "盐酸"],
    "질산": ["질산", "nitric acid", "HNO3", "硝酸"],
    "인산": ["인산", "phosphoric acid", "H3PO4", "磷酸"],
    "TMAH": ["TMAH", "수산화테트라메틸암모늄", "tetramethylammonium", "현상액", "显影液"],
    "아세톤": ["아세톤", "acetone", "丙酮"],
    "메탄올": ["메탄올", "메틸알코올", "methanol", "甲醇"],
    "IPA": ["IPA", "이소프로필알코올", "이소프로판올", "isopropanol", "isopropyl alcohol", "异丙醇"],
    "PGMEA": ["PGMEA", "propylene glycol monomethyl ether acetate", "丙二醇甲醚醋酸酯"],
    "수산화나트륨": ["수산화나트륨", "가성소다", "양잿물", "sodium hydroxide", "NaOH", "氢氧化钠"],
}


def _alias_pattern(alias: str) -> re.Pattern:
    """영문·화학식은 단어 경계로 찾는다 (HF 가 HFC 에 걸리지 않도록). 한글·한자는 그대로."""
    if re.fullmatch(r"[A-Za-z0-9 ]+", alias):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", re.I)
    return re.compile(re.escape(alias))


_PATTERNS = {substance: [_alias_pattern(a) for a in aliases] for substance, aliases in ALIASES.items()}


@lru_cache(maxsize=4)
def _products_by_substance(store_id: int) -> Dict[str, Set[str]]:
    store = get_store(TOPIC_CHEMICAL)
    found: Dict[str, Set[str]] = {}
    for doc in store.docstore._dict.values():
        md = doc.metadata
        if md.get("doc_type") == DOC_TYPE_MSDS and md.get("substance") and md.get("product_id"):
            found.setdefault(md["substance"], set()).add(md["product_id"])
    return found


def products_by_substance() -> Dict[str, Set[str]]:
    """인덱스(faiss_db/msds)의 물질 → 제품 목록. 인덱스가 없으면 {}."""
    store = get_store(TOPIC_CHEMICAL)
    return _products_by_substance(id(store)) if store is not None else {}


def mentioned_substances(question: str) -> Set[str]:
    """질문에 나온 물질 (ALIASES 기준)."""
    return {s for s, pats in _PATTERNS.items() if any(p.search(question) for p in pats)}


def resolve_product_id(question: str, topic: str, language: str = "ko",
                       product_id: Optional[str] = None, equipment_id: Optional[str] = None) -> Optional[str]:
    """요청 product_id 가 있으면 그대로. 없으면 질문의 물질명으로 제품 하나를 정한다 (못 정하면 None)."""
    if product_id or topic != TOPIC_CHEMICAL:
        return product_id
    table = products_by_substance()
    if not table:
        return None
    text = question if language == "ko" else f"{question} {to_korean(question, language)}"
    candidates = set()
    for substance in mentioned_substances(text):
        candidates |= table.get(substance, set())
    allowed = equipment.product_ids(equipment_id)
    if allowed is not None:
        candidates &= set(allowed)
    return candidates.pop() if len(candidates) == 1 else None
