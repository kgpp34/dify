# -*- coding: UTF-8 -*-
"""
@Project : api
@File    : cffex_rag_model_config.py
@Author  : yanglh
@Data    : 2024/11/27 11:22
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class CffexRagModelConfig(BaseSettings):
    """
    Configuration settings for Cffex Internal RAG Model
    """

    RAG_MODEL_INTERFACE_BASE_URL: Optional[str] = Field(
        description="Cffex Internal RAG model Interface Base url",
        default="172.31.73.27",
    )

    RAG_PROXY_BEAR_TOKEN: Optional[str] = Field(
        description="Rag proxy model bear token",
        default="cffex-s2bs3omfmxl32rpw"
    )

    RAG_EMBEDDING_ENDPOINT: Optional[str] = Field(
        description="Embedding model interface endpoint",
        default="/rag_service/get_embeddings_dev"
    )

    RAG_MODEL_ENDPOINT: Optional[str] = Field(
        description="Embedding model info interface endpoint",
        default="/rag_service/get_models_dev"
    )

    RAG_DEFAULT_SPARSE_EMBEDDING: Optional[str] = Field(
        description="Default sparse embedding model",
        default="bge_m3_all"
    )
