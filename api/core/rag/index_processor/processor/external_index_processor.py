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


class ExternalIndexProcessor(BaseIndexProcessor):

    def __init__(self, server_address: str, request_timeout: int = 300000):
        self._http_client = HttpClient(base_url=server_address, timeout=request_timeout)
        self.api_key = "app-u25lJyWklpiesnRnBmao3Z9S"
        self.document = None

    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        server_address = self._http_client.base_url
        upload_file_id = extract_setting.upload_file.id
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "inputs": {
                "orig_mail": [{
                    "transfer_method": "local_file",
                    "upload_file_id": upload_file_id,
                    "type": "document"
                }]
            },
            "response_mode": "blocking",
            "user": "abc-123",
        }
        response = requests.post(server_address, headers=headers, json=data)
        if response.status_code == 200:
            response_data  = response.json()
            print(response_data)
            outputs = response_data.get('data', {}).get('outputs', {})
            if outputs:
                result = outputs.get("result", {})
                documents = []
                for doc_data in result.get("documents", []):
                    doc = Document(
                        page_content=doc_data.get("page_content", "test"),
                        metadata=doc_data.get("metadata", {})
                    )
                    documents.append(doc)
                if documents == []:
                    doc = Document(
                        page_content="test",
                        metadata={}
                    )
                    documents.append(doc)
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