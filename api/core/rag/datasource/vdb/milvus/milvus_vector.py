import json
import logging
import numpy as np
from scipy.sparse import csr_array, vstack

from typing import Any, Optional

from pydantic import BaseModel, model_validator
from pymilvus import MilvusClient, MilvusException
from pymilvus.milvus_client import IndexParams

from configs import dify_config
from core.rag.datasource.vdb.field import Field
from core.rag.datasource.vdb.vector_base import BaseVector
from core.rag.datasource.vdb.vector_factory import AbstractVectorFactory
from core.rag.datasource.vdb.vector_type import VectorType
from core.rag.embedding.embedding_base import Embeddings
from core.rag.models.document import Document
from extensions.ext_redis import redis_client
from models.dataset import Dataset
from services.model_proxy.http_proxy import HttpProxy

logger = logging.getLogger(__name__)


class CffexRagModelConfig(BaseModel):
    base_url: str = None
    embedding_endpoint: str = None
    model_endpoint: str = None
    sparse_embedding_model: str = None
    bear_token: str = None

    @model_validator(mode="before")
    @classmethod
    def validate_config(cls, values: dict) -> dict:
        if not values.get("base_url"):
            raise ValueError("config RAG_MODEL_INTERFACE_BASE_URL is required")
        return values


class MilvusConfig(BaseModel):
    uri: str
    token: Optional[str] = None
    user: str
    password: str
    batch_size: int = 100
    database: str = "default"

    @model_validator(mode="before")
    @classmethod
    def validate_config(cls, values: dict) -> dict:
        if not values.get("uri"):
            raise ValueError("config MILVUS_URI is required")
        if not values.get("user"):
            raise ValueError("config MILVUS_USER is required")
        if not values.get("password"):
            raise ValueError("config MILVUS_PASSWORD is required")
        return values

    def to_milvus_params(self):
        return {
            "uri": self.uri,
            "token": self.token,
            "user": self.user,
            "password": self.password,
            "db_name": self.database,
        }


def stack_sparse_embeddings(sparse_embs):
    return vstack([sparse_emb.reshape((1,-1)) for sparse_emb in sparse_embs])


class MilvusVector(BaseVector):
    def __init__(self, collection_name: str, config: MilvusConfig, customConfig: CffexRagModelConfig = None):
        super().__init__(collection_name)
        self._client_config = config
        self._custom_model_config = customConfig
        self._client = self._init_client(config)
        self._consistency_level = "Session"
        self._fields = []

        if self._custom_model_config.base_url is not None:
            # Initialize the client with a base URL and optional headers
            self.model_proxy_client = HttpProxy(base_url=self._custom_model_config.base_url,
                                                headers={"Authorization": self._custom_model_config.bear_token})
            # Obtain proxy model information
            self.model_info = self.model_proxy_client.get(endpoint=self._custom_model_config.model_endpoint)

    def get_type(self) -> str:
        return VectorType.MILVUS

    def create(self, texts: list[Document], embeddings: list[list[float]], **kwargs):
        index_params = {"metric_type": "IP", "index_type": "HNSW", "params": {"M": 8, "efConstruction": 64}}
        metadatas = [d.metadata for d in texts]
        # call internal model proxy to obtain sparse vector
        sparse_embeddings = self._generate_sparse_vector(texts)
        self.create_collection(embeddings, sparse_embeddings, metadatas, index_params)
        self.add_texts(texts, embeddings, sparse_embeddings)

    def add_texts(self, documents: list[Document], embeddings: list[list[float]],
                  sparse_embeddings: list[list[float]] = None, **kwargs):
        insert_dict_list = []
        for i in range(len(documents)):
            insert_dict = {
                Field.CONTENT_KEY.value: documents[i].page_content,
                # ADD DENSE_VECTOR
                Field.VECTOR.value: embeddings[i],
                Field.METADATA_KEY.value: documents[i].metadata,
            }
            if sparse_embeddings:
                # ADD SPARSE_VECTOR
                insert_dict[Field.SPARSE_VECTOR.value] = sparse_embeddings[i]
            insert_dict_list.append(insert_dict)
        # Total insert count
        total_count = len(insert_dict_list)

        pks: list[str] = []

        for i in range(0, total_count, 1000):
            batch_insert_list = insert_dict_list[i: i + 1000]
            # Insert into the collection.
            try:
                ids = self._client.insert(collection_name=self._collection_name, data=batch_insert_list)
                pks.extend(ids)
            except MilvusException as e:
                logger.exception("Failed to insert batch starting at entity: %s/%s", i, total_count)
                raise e
        return pks

    def get_ids_by_metadata_field(self, key: str, value: str):
        result = self._client.query(
            collection_name=self._collection_name, filter=f'metadata["{key}"] == "{value}"', output_fields=["id"]
        )
        if result:
            return [item["id"] for item in result]
        else:
            return None

    def delete_by_metadata_field(self, key: str, value: str):
        if self._client.has_collection(self._collection_name):
            ids = self.get_ids_by_metadata_field(key, value)
            if ids:
                self._client.delete(collection_name=self._collection_name, pks=ids)

    def delete_by_ids(self, ids: list[str]) -> None:
        if self._client.has_collection(self._collection_name):
            result = self._client.query(
                collection_name=self._collection_name, filter=f'metadata["doc_id"] in {ids}', output_fields=["id"]
            )
            if result:
                ids = [item["id"] for item in result]
                self._client.delete(collection_name=self._collection_name, pks=ids)

    def delete(self) -> None:
        if self._client.has_collection(self._collection_name):
            self._client.drop_collection(self._collection_name, None)

    def text_exists(self, id: str) -> bool:
        if not self._client.has_collection(self._collection_name):
            return False

        result = self._client.query(
            collection_name=self._collection_name, filter=f'metadata["doc_id"] == "{id}"', output_fields=["id"]
        )

        return len(result) > 0

    def search_by_vector(self, query_vector: list[float], **kwargs: Any) -> list[Document]:
        if "query" in kwargs and kwargs.get("vec_type") == "sparse":
            query_embedding = self._get_sparse_embeddings([kwargs.get("query")])
            query_vector = query_embedding[0]

            # Set search parameters.
        results = self._client.search(
            collection_name=self._collection_name,
            anns_field=Field.SPARSE_VECTOR.value if kwargs.get("vec_type") == "sparse" else Field.VECTOR.value,
            data=[query_vector],
            limit=kwargs.get("top_k", 4),
            output_fields=[Field.CONTENT_KEY.value, Field.METADATA_KEY.value],
        )
        # Organize results.
        docs = []
        for result in results[0]:
            metadata = result["entity"].get(Field.METADATA_KEY.value)
            metadata["score"] = result["distance"]
            score_threshold = float(kwargs.get("score_threshold") or 0.0)
            if result["distance"] > score_threshold:
                doc = Document(page_content=result["entity"].get(Field.CONTENT_KEY.value), metadata=metadata)
                docs.append(doc)
        return docs

    def search_by_full_text(self, query: str, **kwargs: Any) -> list[Document]:
        # milvus/zilliz doesn't support bm25 search
        return []

    def create_collection(
            self, embeddings: list, sparse_embeddings: list, metadatas: Optional[list[dict]] = None,
            index_params: Optional[dict] = None
    ):
        lock_name = "vector_indexing_lock_{}".format(self._collection_name)
        with redis_client.lock(lock_name, timeout=20):
            collection_exist_cache_key = "vector_indexing_{}".format(self._collection_name)
            if redis_client.get(collection_exist_cache_key):
                return
            # Grab the existing collection if it exists
            if not self._client.has_collection(self._collection_name):
                from pymilvus import CollectionSchema, DataType, FieldSchema
                from pymilvus.orm.types import infer_dtype_bydata

                # Determine embedding dim
                dim = len(embeddings[0])
                fields = []
                if metadatas:
                    fields.append(FieldSchema(Field.METADATA_KEY.value, DataType.JSON, max_length=65_535))

                # Create the text field
                fields.append(FieldSchema(Field.CONTENT_KEY.value, DataType.VARCHAR, max_length=65_535))
                # Create the primary key field
                fields.append(FieldSchema(Field.PRIMARY_KEY.value, DataType.INT64, is_primary=True, auto_id=True))
                # Create the vector field, supports binary or float vectors
                fields.append(FieldSchema(Field.VECTOR.value, infer_dtype_bydata(embeddings[0]), dim=dim))
                # Create the sparse vector field
                if sparse_embeddings and len(sparse_embeddings) > 0:
                    fields.append(FieldSchema(Field.SPARSE_VECTOR.value, DataType.SPARSE_FLOAT_VECTOR))
                # Create the schema for the collection
                schema = CollectionSchema(fields)

                for x in schema.fields:
                    self._fields.append(x.name)
                # Since primary field is auto-id, no need to track it
                self._fields.remove(Field.PRIMARY_KEY.value)

                # Create Index params for the collection
                index_params_obj = IndexParams()
                index_params_obj.add_index(field_name=Field.VECTOR.value, **index_params)

                # Create the collection
                collection_name = self._collection_name
                self._client.create_collection(
                    collection_name=collection_name,
                    schema=schema,
                    index_params=index_params_obj,
                    consistency_level=self._consistency_level,
                )
            redis_client.set(collection_exist_cache_key, 1, ex=3600)

    def _init_client(self, config) -> MilvusClient:
        client = MilvusClient(uri=config.uri, user=config.user, password=config.password, db_name=config.database)
        return client

    def _generate_sparse_vector(self, documents: list[Document]) -> list[list[float]]:
        """
        call internal rag model interface to obtain sparse vector
        Args:
            text: raw document

        Returns:

        """
        """
            调用内部 RAG 模型接口以获取稀疏向量
            Args:
                documents: 原始文档列表

            Returns:
                稀疏向量列表
            """
        if self.model_proxy_client is not None:
            embedding_texts = [document.page_content for document in documents]
            sparse_embeddings = self._get_sparse_embeddings(embedding_texts)
            return sparse_embeddings

    def _get_sparse_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        获取稀疏嵌入的公共方法
        Args:
            texts: 需要获取稀疏嵌入的文本列表

        Returns:
            稀疏嵌入列表
        """
        query = {
            "sentences": texts,
            "model_name": self._custom_model_config.sparse_embedding_model
        }
        # embedding
        embedding_result = self.model_proxy_client.post(endpoint=self._custom_model_config.embedding_endpoint,
                                                        data=query)

        sparse_embeddings = []

        sparse_dim = 250002
        if self.model_info:
            for model in self.model_info["embedding_model"]:
                if model["id"] == self._custom_model_config.sparse_embedding_model:
                    sparse_dim = model["sparse_dim"]

        for emb in embedding_result["data"]:
            sparsest = []
            for sparse_vec in emb["embedding"]["sparse"]:

                indices = [int(k) for k in sparse_vec]
                values = np.array(list(sparse_vec.values()), dtype=np.float64)
                row_indices = [0] * len(indices)
                csr = csr_array((values, (row_indices, indices)), shape=(1, sparse_dim))
                sparsest.append(csr)
            sparse_embeddings.append(stack_sparse_embeddings(sparsest).tocsr())

        return sparse_embeddings


class MilvusVectorFactory(AbstractVectorFactory):
    def init_vector(self, dataset: Dataset, attributes: list, embeddings: Embeddings) -> MilvusVector:
        if dataset.index_struct_dict:
            class_prefix: str = dataset.index_struct_dict["vector_store"]["class_prefix"]
            collection_name = class_prefix
        else:
            dataset_id = dataset.id
            collection_name = Dataset.gen_collection_name_by_id(dataset_id)
            dataset.index_struct = json.dumps(self.gen_index_struct_dict(VectorType.MILVUS, collection_name))

        return MilvusVector(
            collection_name=collection_name,
            config=MilvusConfig(
                uri=dify_config.MILVUS_URI,
                token=dify_config.MILVUS_TOKEN,
                user=dify_config.MILVUS_USER,
                password=dify_config.MILVUS_PASSWORD,
                database=dify_config.MILVUS_DATABASE,
            ),
            customConfig=CffexRagModelConfig(
                base_url=dify_config.RAG_MODEL_INTERFACE_BASE_URL,
                embedding_endpoint=dify_config.RAG_EMBEDDING_ENDPOINT,
                model_endpoint=dify_config.RAG_MODEL_ENDPOINT,
                sparse_embedding_model=dify_config.RAG_DEFAULT_SPARSE_EMBEDDING,
                bear_token=dify_config.RAG_PROXY_BEAR_TOKEN
            )
        )
