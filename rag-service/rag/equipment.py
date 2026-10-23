"""가상 장비 → 사용 물질(product_id) 매핑 — 담당: 김규빈

data/equipment_map.json 을 읽어 장비 ID 로 검색 범위(제품 목록)와 자료 범위(coverage)를 알려 준다.
장비 답변의 근거는 이 표가 아니라 MSDS · KOSHA · S1 원문 검색 결과다 (이 표는 범위만 정한다).
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "equipment_map.json"


@lru_cache(maxsize=1)
def _load() -> Dict[str, dict]:
    if not MAP_PATH.exists():
        return {}
    with open(MAP_PATH, encoding="utf-8") as f:
        return {e["equipment_id"]: e for e in json.load(f)["equipment"]}


def get(equipment_id: Optional[str]) -> Optional[dict]:
    """장비 정보. 모르는 ID 거나 None 이면 None."""
    return _load().get(equipment_id) if equipment_id else None


def product_ids(equipment_id: Optional[str]) -> Optional[List[str]]:
    """장비에서 쓰는 제품 목록. 모르는 장비면 None (범위 제한 없음), 자료 미등록 장비면 []."""
    e = get(equipment_id)
    return list(e["product_ids"]) if e else None


def is_unregistered(equipment_id: Optional[str]) -> bool:
    """사용 물질의 안전자료가 등록되지 않은 장비인가 (coverage == "none") → handoff."""
    e = get(equipment_id)
    return bool(e) and e.get("coverage") == "none"
