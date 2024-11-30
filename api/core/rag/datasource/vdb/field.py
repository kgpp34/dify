from enum import Enum


class Field(Enum):
    CONTENT_KEY = "page_content"
    METADATA_KEY = "metadata"
    GROUP_KEY = "group_id"
    VECTOR = "vector"
    SPARSE_VECTOR = "sparse_vector"
    BM25_VECTOR = "bm25_vector"
    TEXT_KEY = "text"
    PRIMARY_KEY = "id"
    DOC_ID = "metadata.doc_id"
