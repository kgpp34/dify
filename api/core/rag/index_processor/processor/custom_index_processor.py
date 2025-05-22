"""Custom index processor."""

import logging
from typing import Optional

from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.models.document import Document
from libs.http_client import HttpClient
from models.dataset import Dataset


class CustomParagraphIndexProcessor(BaseIndexProcessor):
    """
    自定义索引处理器，通过调用用户提供的服务地址来完成extract和transform方法。
    其余方法使用ParagraphIndexProcessor的默认实现。
    """

    def __init__(self, server_address: str, request_timeout: int = 300):
        """
        初始化自定义索引处理器。

        Args:
            server_address: 用户提供的服务地址
            request_timeout: 请求超时时间（秒）
        """
        self._http_client = HttpClient(base_url=server_address, timeout=request_timeout)

    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        """
        调用用户自定义服务的extract方法。

        Args:
            extract_setting: 提取设置
            **kwargs: 其他参数

        Returns:
            提取的文档列表
        """
        # 准备请求数据
        request_data = {"extract_setting": extract_setting.model_dump(), "kwargs": kwargs}
        # 调用自定义服务
        try:
            response_data = self._http_client.post("/extract", json_data=request_data)

            # 转换为Document对象
            documents = []
            for doc_data in response_data.get("documents", []):
                doc = Document(page_content=doc_data.get("page_content", ""), metadata=doc_data.get("metadata", {}))
                documents.append(doc)

            return documents
        except Exception as e:
            logging.exception("调用自定义extract服务失败")
            raise RuntimeError(f"调用自定义extract服务失败: {str(e)}")

    def transform(self, documents: list[Document], **kwargs) -> list[Document]:
        """
        调用用户自定义服务的transform方法。

        Args:
            documents: 待转换的文档列表
            **kwargs: 其他参数

        Returns:
            转换后的文档列表
        """
        # 准备请求数据
        request_data = {
            "documents": [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in documents],
            "kwargs": kwargs,
        }

        # 调用自定义服务
        try:
            response_data = self._http_client.post("/transform", json_data=request_data)

            # 转换为Document对象
            transformed_documents = []
            for doc_data in response_data.get("documents", []):
                doc = Document(page_content=doc_data.get("page_content", ""), metadata=doc_data.get("metadata", {}))
                transformed_documents.append(doc)

            return transformed_documents
        except Exception as e:
            logging.exception("调用自定义transform服务失败")
            raise RuntimeError(f"调用自定义transform服务失败: {str(e)}")

    def load(self, dataset: Dataset, documents: list[Document], with_keywords: bool = True, **kwargs):
        if dataset.indexing_technique == "high_quality":
            vector = Vector(dataset)
            vector.create(documents)
        if with_keywords:
            keywords_list = kwargs.get("keywords_list")
            keyword = Keyword(dataset)
            if keywords_list and len(keywords_list) > 0:
                keyword.add_texts(documents, keywords_list=keywords_list)
            else:
                keyword.add_texts(documents)

    def clean(self, dataset: Dataset, node_ids: Optional[list[str]], with_keywords: bool = True, **kwargs):
        """使用默认的ParagraphIndexProcessor实现"""
        if dataset.indexing_technique == "high_quality":
            vector = Vector(dataset)
            if node_ids:
                vector.delete_by_ids(node_ids)
            else:
                vector.delete()
        if with_keywords:
            keyword = Keyword(dataset)
            if node_ids:
                keyword.delete_by_ids(node_ids)
            else:
                keyword.delete()

    def retrieve(
        self,
        retrieval_method: str,
        query: str,
        dataset: Dataset,
        top_k: int,
        score_threshold: float,
        reranking_model: dict,
    ) -> list[Document]:
        """使用默认的ParagraphIndexProcessor实现"""
        # Set search parameters.
        results = RetrievalService.retrieve(
            retrieval_method=retrieval_method,
            dataset_id=dataset.id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            reranking_model=reranking_model,
        )
        # Organize results.
        docs = []
        for result in results:
            metadata = result.metadata
            metadata["score"] = result.score
            if result.score > score_threshold:
                doc = Document(page_content=result.page_content, metadata=metadata)
                docs.append(doc)
        return docs
