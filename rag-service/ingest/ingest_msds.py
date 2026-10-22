"""MSDS → 16개 항목 단위 청킹 → 메타데이터 부착 → FAISS 적재 — 담당: 윤서진

메타데이터 키는 rag/schema.py 의 ChunkMeta (공통 + MSDS 전용) 를 따른다.
원문 PDF 는 data/msds/, 인덱스는 schema.INDEX_DIRS[TOPIC_CHEMICAL].
법령 적재는 기존 ingest_law.py (메타데이터에 doc_id · topic · title · section 추가 필요).
"""
from typing import List

from rag.schema import ChunkMeta


def split_sections(text: str) -> List[dict]:
    """MSDS 본문을 1~16 항목으로 나눈다. [{"no": 8, "title": "노출방지 및 개인보호구", "body": ...}]"""
    # TODO
    raise NotImplementedError


def build_chunks(text: str, doc_id: str, product_id: str, substance: str, supplier: str,
                 cas_no: str, revision_date: str, source_url: str) -> List[dict]:
    """항목마다 {"page_content": ..., "metadata": ChunkMeta} 를 만든다. section = "8. 노출방지 및 개인보호구"."""
    # TODO
    raise NotImplementedError


def main() -> None:
    """argparse: --input --doc-id --product-id ... --append --dry-run (ingest_law.py 와 같은 사용법)."""
    # TODO
    raise NotImplementedError


if __name__ == "__main__":
    main()
