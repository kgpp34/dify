import base64
import json
import logging
from typing import Optional

import requests
from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from libs.http_client import HttpClient
from models import Document, Dataset
from core.rag.models.document import Document

from core.rag.extractor.entity.external_response import ResponseData, OutputResult, DocumentResult

from core.rag.extractor.entity.external_response_type import ExternalResponseEnum
from extensions.ext_storage import storage
from extensions.storage.opendal_storage import OpenDALStorage
from extensions.ext_storage import Storage
from extensions.storage.storage_type import StorageType


class ExternalIndexProcessor(BaseIndexProcessor):

    def __init__(self, server_address: str, api_key: str, user: str):
        self._http_client = HttpClient(base_url=server_address)
        self.server_address = server_address
        self.api_key = api_key
        self.user = user
        self.document = None

    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        upload_file = extract_setting.upload_file
        storage = OpenDALStorage(scheme="fs")
        file_bytes: bytes = storage.load_once(upload_file.key)
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "transfer_method": "base64",
            "file_name": upload_file.name,
            "file_data": file_base64,
            "user": self.user,
        }
        logging.info(f"Request to {self.server_address} with data: {data}")
        response = self._http_client.post(endpoint="", headers=headers, data=json.dumps(data))
        logging.info(f"Response from {self.server_address}: {response}")
        parsed_response = ResponseData.from_dict(response)
        outputs = parsed_response.data.get(ExternalResponseEnum.OUTPUTS, {})
        if outputs:
            output_result = OutputResult.from_dict(outputs)
            documents = []
            for doc_data in output_result.result.get(ExternalResponseEnum.DOCUMENTS, []):
                doc = DocumentResult.from_dict(doc_data)
                documents.append(Document(page_content=doc.page_content, metadata=doc.metadata))

            self.document = documents
            return documents

        return None

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