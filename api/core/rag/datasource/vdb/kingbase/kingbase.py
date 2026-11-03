import hashlib
import json
import logging
import re
import uuid
from contextlib import contextmanager
from typing import Any

import psycopg2.errors
import psycopg2.extras  # type: ignore
import psycopg2.pool  # type: ignore
from pydantic import BaseModel, model_validator

from configs import dify_config
from core.rag.datasource.vdb.vector_base import BaseVector
from core.rag.datasource.vdb.vector_factory import AbstractVectorFactory
from core.rag.datasource.vdb.vector_type import VectorType
from core.rag.embedding.embedding_base import Embeddings
from core.rag.models.document import Document
from extensions.ext_redis import redis_client
from models.dataset import Dataset

logger = logging.getLogger(__name__)

# KingbaseES speaks the PostgreSQL wire protocol and its KES_Vector extension is
# compatible with pgvector, so most statements below are shared with the pgvector
# implementation. The KingbaseES specific parts are:
#   * the table DDL does not use a table access method (`USING heap`), KES has no
#     table access method support;
#   * every distance ordering uses `NULLS LAST`, which KES requires to use a
#     vector index under its SQL Server compatible mode and is a no-op otherwise;
#   * the vector value is written as a text literal instead of relying on the
#     `float4[] -> vector` assignment cast;
#   * full text search always spells out the text search configuration so the
#     query can use the GIN index, and so that Chinese segmentation (for example
#     `jiebacfg` from the `sys_jieba` extension) can be enabled by configuration;
#   * `hnsw.ef_search` is raised when `top_k` exceeds the default of 40, otherwise
#     the index silently returns at most 40 rows;
#   * index names are derived from a hash of the table name because KES/PG index
#     names are unique per schema and Dify table names are already close to the
#     63 byte identifier limit.

# default of `hnsw.ef_search` in KES_Vector, see the KES_Vector manual
DEFAULT_HNSW_EF_SEARCH = 40
# KES_Vector can index at most 2000 dimensions of an FP32 vector
MAX_INDEX_DIMENSION = 2000

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {table_name} (
    id UUID PRIMARY KEY,
    text TEXT NOT NULL,
    meta JSONB NOT NULL,
    embedding vector({dimension}) NOT NULL
);
"""

SQL_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
"""

SQL_CREATE_FTS_INDEX = """
CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}
USING gin (to_tsvector('{fts_config}', text));
"""


class KingbaseConfig(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str
    min_connection: int
    max_connection: int
    fts_config: str = "simple"
    enable_seqscan_off: bool = False

    @model_validator(mode="before")
    @classmethod
    def validate_config(cls, values: dict) -> dict:
        if not values["host"]:
            raise ValueError("config KINGBASE_HOST is required")
        if not values["port"]:
            raise ValueError("config KINGBASE_PORT is required")
        if not values["user"]:
            raise ValueError("config KINGBASE_USER is required")
        if not values["password"]:
            raise ValueError("config KINGBASE_PASSWORD is required")
        if not values["database"]:
            raise ValueError("config KINGBASE_DATABASE is required")
        if not values["min_connection"]:
            raise ValueError("config KINGBASE_MIN_CONNECTION is required")
        if not values["max_connection"]:
            raise ValueError("config KINGBASE_MAX_CONNECTION is required")
        if values["min_connection"] > values["max_connection"]:
            raise ValueError("config KINGBASE_MIN_CONNECTION should less than KINGBASE_MAX_CONNECTION")
        # the text search configuration is interpolated into the statements, it must
        # never be able to carry anything but a plain identifier
        fts_config = values.get("fts_config")
        if fts_config and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fts_config):
            raise ValueError("config KINGBASE_FTS_CONFIG must be a valid text search configuration name")
        return values


class Kingbase(BaseVector):
    def __init__(self, collection_name: str, config: KingbaseConfig):
        super().__init__(collection_name)
        self.pool = self._create_connection_pool(config)
        self.table_name = f"embedding_{collection_name}"
        self.fts_config = config.fts_config
        self.enable_seqscan_off = config.enable_seqscan_off

    def get_type(self) -> str:
        return VectorType.KINGBASE

    def _create_connection_pool(self, config: KingbaseConfig):
        return psycopg2.pool.SimpleConnectionPool(
            config.min_connection,
            config.max_connection,
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            client_encoding="UTF8",
        )

    @contextmanager
    def _get_cursor(self):
        conn = self.pool.getconn()
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
            conn.commit()
            self.pool.putconn(conn)

    def _index_name(self, prefix: str) -> str:
        """Build a schema unique index name that stays well below the identifier limit."""
        digest = hashlib.md5(self.table_name.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}_idx"

    @staticmethod
    def _format_vector(embedding: list[float]) -> str:
        """Render a vector as the text literal understood by KES_Vector."""
        return "[" + ",".join(repr(float(value)) for value in embedding) + "]"

    def _apply_query_options(self, cur, top_k: int) -> None:
        if top_k > DEFAULT_HNSW_EF_SEARCH:
            # hnsw returns at most `ef_search` rows, so a larger top_k silently
            # returns fewer documents unless the candidate list is widened
            cur.execute(f"SET LOCAL hnsw.ef_search = {int(top_k)}")
        if self.enable_seqscan_off:
            cur.execute("SET LOCAL enable_seqscan = off")

    def create(self, texts: list[Document], embeddings: list[list[float]], **kwargs):
        dimension = len(embeddings[0])
        self._create_collection(dimension)
        return self.add_texts(texts, embeddings)

    def add_texts(self, documents: list[Document], embeddings: list[list[float]], **kwargs):
        values = []
        pks = []
        for i, doc in enumerate(documents):
            if doc.metadata is not None:
                doc_id = doc.metadata.get("doc_id", str(uuid.uuid4()))
                pks.append(doc_id)
                values.append(
                    (
                        doc_id,
                        doc.page_content,
                        json.dumps(doc.metadata),
                        self._format_vector(embeddings[i]),
                    )
                )
        with self._get_cursor() as cur:
            psycopg2.extras.execute_values(
                cur, f"INSERT INTO {self.table_name} (id, text, meta, embedding) VALUES %s", values
            )
        return pks

    def text_exists(self, id: str) -> bool:
        with self._get_cursor() as cur:
            cur.execute(f"SELECT id FROM {self.table_name} WHERE id = %s", (id,))
            return cur.fetchone() is not None

    def get_by_ids(self, ids: list[str]) -> list[Document]:
        with self._get_cursor() as cur:
            cur.execute(f"SELECT meta, text FROM {self.table_name} WHERE id IN %s", (tuple(ids),))
            docs = []
            for record in cur:
                docs.append(Document(page_content=record[1], metadata=record[0]))
        return docs

    def delete_by_ids(self, ids: list[str]) -> None:
        # Avoiding crashes caused by performing delete operations on empty lists in certain scenarios
        # Scenario 1: extract a document fails, resulting in a table not being created.
        # Then clicking the retry button triggers a delete operation on an empty list.
        if not ids:
            return
        with self._get_cursor() as cur:
            try:
                cur.execute(f"DELETE FROM {self.table_name} WHERE id IN %s", (tuple(ids),))
            except psycopg2.errors.UndefinedTable:
                # table not exists
                logger.warning("Table %s not found, skipping delete operation.", self.table_name)
                return
            except Exception as e:
                raise e

    def delete_by_metadata_field(self, key: str, value: str) -> None:
        with self._get_cursor() as cur:
            cur.execute(f"DELETE FROM {self.table_name} WHERE meta->>%s = %s", (key, value))

    def search_by_vector(self, query_vector: list[float], **kwargs: Any) -> list[Document]:
        """
        Search the nearest neighbors to a vector.

        :param query_vector: The input vector to search for similar items.
        :return: List of Documents that are nearest to the query vector.
        """
        top_k = kwargs.get("top_k", 4)
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        document_ids_filter = kwargs.get("document_ids_filter")
        where_clause = ""
        if document_ids_filter:
            document_ids = ", ".join(f"'{id}'" for id in document_ids_filter)
            where_clause = f" WHERE meta->>'document_id' in ({document_ids}) "

        with self._get_cursor() as cur:
            self._apply_query_options(cur, top_k)
            cur.execute(
                f"SELECT meta, text, embedding <=> %s AS distance FROM {self.table_name}"
                f" {where_clause}"
                f" ORDER BY distance NULLS LAST LIMIT {top_k}",
                (self._format_vector(query_vector),),
            )
            docs = []
            score_threshold = float(kwargs.get("score_threshold") or 0.0)
            for record in cur:
                metadata, text, distance = record
                score = 1 - distance
                metadata["score"] = score
                if score > score_threshold:
                    docs.append(Document(page_content=text, metadata=metadata))
        return docs

    def search_by_full_text(self, query: str, **kwargs: Any) -> list[Document]:
        if not self.fts_config:
            raise ValueError(
                "config KINGBASE_FTS_CONFIG is empty, full text search is disabled for the kingbase vector store. "
                "Set KINGBASE_FTS_CONFIG to a text search configuration (for example `simple` or `jiebacfg`) to "
                "enable it."
            )
        top_k = kwargs.get("top_k", 5)
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        document_ids_filter = kwargs.get("document_ids_filter")
        where_clause = ""
        if document_ids_filter:
            document_ids = ", ".join(f"'{id}'" for id in document_ids_filter)
            where_clause = f" AND meta->>'document_id' in ({document_ids}) "

        with self._get_cursor() as cur:
            if self.enable_seqscan_off:
                cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute(
                f"""SELECT meta, text, ts_rank(to_tsvector(%s, text), plainto_tsquery(%s, %s)) AS score
                FROM {self.table_name}
                WHERE to_tsvector(%s, text) @@ plainto_tsquery(%s, %s)
                {where_clause}
                ORDER BY score DESC
                LIMIT {top_k}""",
                (self.fts_config, self.fts_config, query, self.fts_config, self.fts_config, query),
            )

            docs = []

            for record in cur:
                metadata, text, score = record
                metadata["score"] = score
                docs.append(Document(page_content=text, metadata=metadata))

        return docs

    def delete(self) -> None:
        with self._get_cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.table_name}")

    def _ensure_extension(self, cur) -> None:
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except psycopg2.Error as e:
            raise RuntimeError(
                "failed to create the KES_Vector extension. The `vector` extension must be installed in the "
                "KingbaseES installation and the configured user needs the privilege to create it "
                "(use a superuser such as `system`, or ask the DBA to run CREATE EXTENSION vector)."
            ) from e

    def _create_fts_index(self) -> None:
        try:
            with self._get_cursor() as cur:
                cur.execute(
                    SQL_CREATE_FTS_INDEX.format(
                        table_name=self.table_name,
                        index_name=self._index_name("embedding_fts"),
                        fts_config=self.fts_config,
                    )
                )
        except psycopg2.Error as e:
            logger.warning(
                "Failed to create the full text index on %s with configuration %s: %s. "
                "Full text search keeps working but without an index.",
                self.table_name,
                self.fts_config,
                e,
            )

    def _create_collection(self, dimension: int):
        cache_key = f"vector_indexing_{self._collection_name}"
        lock_name = f"{cache_key}_lock"
        with redis_client.lock(lock_name, timeout=20):
            collection_exist_cache_key = f"vector_indexing_{self._collection_name}"
            if redis_client.get(collection_exist_cache_key):
                return

            with self._get_cursor() as cur:
                self._ensure_extension(cur)
                cur.execute(SQL_CREATE_TABLE.format(table_name=self.table_name, dimension=dimension))
                # KES_Vector indexes at most 2000 dimensions of a vector column
                if dimension <= MAX_INDEX_DIMENSION:
                    cur.execute(
                        SQL_CREATE_INDEX.format(
                            table_name=self.table_name,
                            index_name=self._index_name("embedding_cosine"),
                        )
                    )
            if self.fts_config:
                self._create_fts_index()
            redis_client.set(collection_exist_cache_key, 1, ex=3600)


class KingbaseVectorFactory(AbstractVectorFactory):
    def init_vector(self, dataset: Dataset, attributes: list, embeddings: Embeddings) -> Kingbase:
        if dataset.index_struct_dict:
            class_prefix: str = dataset.index_struct_dict["vector_store"]["class_prefix"]
            collection_name = class_prefix
        else:
            dataset_id = dataset.id
            collection_name = Dataset.gen_collection_name_by_id(dataset_id)
            dataset.index_struct = json.dumps(self.gen_index_struct_dict(VectorType.KINGBASE, collection_name))

        return Kingbase(
            collection_name=collection_name,
            config=KingbaseConfig(
                host=dify_config.KINGBASE_HOST or "localhost",
                port=dify_config.KINGBASE_PORT,
                user=dify_config.KINGBASE_USER or "system",
                password=dify_config.KINGBASE_PASSWORD or "",
                database=dify_config.KINGBASE_DATABASE or "dify",
                min_connection=dify_config.KINGBASE_MIN_CONNECTION,
                max_connection=dify_config.KINGBASE_MAX_CONNECTION,
                fts_config=dify_config.KINGBASE_FTS_CONFIG or "",
                enable_seqscan_off=dify_config.KINGBASE_ENABLE_SEQSCAN_OFF or False,
            ),
        )
