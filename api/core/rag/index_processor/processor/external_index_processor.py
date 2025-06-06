import base64
import json
import logging
from typing import Optional

from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.extractor.entity.external_response import DocumentResult, ResponseData
from core.rag.extractor.entity.external_response_type import ExternalResponseEnum
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.models.document import Document
from extensions.ext_storage import storage
from libs.http_client import HttpClient

# from models import Document, Dataset
from models import Dataset


class ExternalIndexProcessor(BaseIndexProcessor):
    def __init__(self, server_address: str):
        self._http_client = HttpClient(base_url=server_address)
        self.server_address = server_address
        self.document: list[Document] = []

    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        upload_file = extract_setting.upload_file
        file_base64 = None
        file_name = None
        if upload_file:
            file_bytes = storage.load_once(upload_file.key)
            file_name = upload_file.name
            file_base64 = base64.b64encode(file_bytes).decode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        data = {"transfer_method": "base64", "file_name": file_name, "file_data": file_base64}
        try:
            response = self._http_client.post(endpoint="", headers=headers, json_data=data)
            parsed_response = ResponseData.from_dict(response)
            documents = []
            document = parsed_response.data.get(ExternalResponseEnum.DOCUMENTS, [])
            for doc_data in document:
                doc = DocumentResult.from_dict(doc_data)
                documents.append(Document(page_content=doc.page_content, metadata=doc.metadata))
            self.document = documents
            return documents
        except Exception as e:
            logging.exception(f"Failed to extract documents from {self.server_address}")
            raise e

    def transform(self, documents: list[Document], **kwargs) -> list[Document]:
        documents = self.document
        return documents

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
