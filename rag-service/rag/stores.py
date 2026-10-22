"""topic 별 FAISS 인덱스 로드 — 담당: 김규빈

서버 시작 시 한 번만 로드하고, 검색은 get_store() 로 가져다 쓴다.
"""
import logging
import os
from typing import Dict, Optional

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from rag.schema import ENV_EMBEDDING_MODEL, INDEX_DIRS

log = logging.getLogger(__name__)

_STORES: Dict[str, FAISS] = {}


def _embeddings() -> OpenAIEmbeddings:
    model = os.getenv(ENV_EMBEDDING_MODEL)
    return OpenAIEmbeddings(model=model) if model else OpenAIEmbeddings()


def load_all() -> None:
    """INDEX_DIRS 의 인덱스를 모두 로드한다. 없는 인덱스는 건너뛰고 경고만 남긴다."""
    emb = _embeddings()
    for topic, path in INDEX_DIRS.items():
        if not os.path.exists(os.path.join(path, "index.faiss")):
            log.warning("인덱스 없음: %s (%s)", topic, path)
            continue
        _STORES[topic] = FAISS.load_local(path, emb, allow_dangerous_deserialization=True)
        log.info("인덱스 로드: %s (%s)", topic, path)


def get_store(topic: str) -> Optional[FAISS]:
    """topic 의 FAISS 인덱스. 로드되지 않았으면 None."""
    return _STORES.get(topic)


def is_ready() -> bool:
    """인덱스가 하나 이상 로드됐는가 (/health 용). topic 별 상태는 status() 로 따로 보여 준다.
    TODO: MSDS 인덱스까지 준비되면 '모든 topic 로드'로 기준을 올린다."""
    return bool(_STORES)


def status() -> Dict[str, bool]:
    """topic 별 로드 여부 (/health 응답 본문용)."""
    return {topic: topic in _STORES for topic in INDEX_DIRS}
