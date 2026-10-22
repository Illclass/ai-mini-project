"""topic 별 FAISS 인덱스 로드 — 담당: 김규빈

서버 시작 시 한 번만 로드하고, 검색은 get_store() 로 가져다 쓴다.
"""
from typing import Optional

from rag.schema import INDEX_DIRS


def load_all() -> None:
    """INDEX_DIRS 의 인덱스를 모두 로드한다. 없는 인덱스는 건너뛰고 경고만 남긴다."""
    # TODO: FAISS.load_local(path, OpenAIEmbeddings(), allow_dangerous_deserialization=True)
    raise NotImplementedError


def get_store(topic: str) -> Optional[object]:
    """topic 의 FAISS 인덱스. 로드되지 않았으면 None."""
    # TODO
    raise NotImplementedError


def is_ready() -> bool:
    """모든 topic 인덱스가 로드됐는가 (/health 용)."""
    # TODO
    raise NotImplementedError
