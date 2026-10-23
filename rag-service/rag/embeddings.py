"""임베딩 모델 — 담당: 김규빈

적재(ingest_law.py · ingest_msds.py)와 검색(stores.py)이 반드시 같은 모델을 쓰도록 여기서만 만든다.
모델이 다르면 오류 없이 검색 결과만 틀어지므로, 모델을 바꾸면 ./ingest_all.sh 로 다시 적재한다.

    EMBEDDING_MODEL=text-embedding-3-small   # OpenAI
    EMBEDDING_MODEL=bge-m3                   # 로컬 실행 (sentence-transformers 필요, 첫 실행 때 약 2GB 다운로드)
"""
import os
from typing import Optional

from rag.schema import DEFAULT_EMBEDDING_MODEL, ENV_EMBEDDING_MODEL

# 로컬(Hugging Face) 모델 별칭 → 모델 저장소 이름
LOCAL_MODELS = {"bge-m3": "BAAI/bge-m3"}


def model_name(model: Optional[str] = None) -> str:
    """인자 → 환경변수 EMBEDDING_MODEL → 기본값 순서로 모델 이름을 정한다."""
    return model or os.getenv(ENV_EMBEDDING_MODEL) or DEFAULT_EMBEDDING_MODEL


def get_embeddings(model: Optional[str] = None):
    """LangChain 임베딩 객체. OpenAI 모델이면 OpenAIEmbeddings, 로컬 모델이면 HuggingFaceEmbeddings."""
    name = model_name(model)
    if name in LOCAL_MODELS:
        from langchain_community.embeddings import HuggingFaceEmbeddings  # 지연 import (torch 로딩이 느림)
        return HuggingFaceEmbeddings(model_name=LOCAL_MODELS[name],
                                     encode_kwargs={"normalize_embeddings": True})
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=name)
