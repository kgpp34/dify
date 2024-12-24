"""Functionality for splitting text."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, List, Optional

from llama_index.core.node_parser import MarkdownNodeParser, SimpleNodeParser
from llama_index.core.schema import BaseNode, Document

from core.model_manager import ModelInstance
from core.model_runtime.model_providers.__base.tokenizers.gpt2_tokenzier import GPT2Tokenizer
from core.rag.splitter.text_splitter import (
    TS,
    Collection,
    Literal,
    RecursiveCharacterTextSplitter,
    Set,
    TokenTextSplitter,
    Union,
)


class EnhanceRecursiveCharacterTextSplitter(RecursiveCharacterTextSplitter):
    """
    This class is used to implement from_gpt2_encoder, to prevent using of tiktoken
    """

    @classmethod
    def from_encoder(
        cls: type[TS],
        embedding_model_instance: Optional[ModelInstance],
        allowed_special: Union[Literal[all], Set[str]] = set(),
        disallowed_special: Union[Literal[all], Collection[str]] = "all",
        **kwargs: Any,
    ):
        def _token_encoder(text: str) -> int:
            if not text:
                return 0

            if embedding_model_instance:
                return embedding_model_instance.get_text_embedding_num_tokens(texts=[text])
            else:
                return GPT2Tokenizer.get_num_tokens(text)

        if issubclass(cls, TokenTextSplitter):
            extra_kwargs = {
                "model_name": embedding_model_instance.model if embedding_model_instance else "gpt2",
                "allowed_special": allowed_special,
                "disallowed_special": disallowed_special,
            }
            kwargs = {**kwargs, **extra_kwargs}

        return cls(length_function=_token_encoder, **kwargs)


class FixedRecursiveCharacterTextSplitter(EnhanceRecursiveCharacterTextSplitter):
    def __init__(self, fixed_separator: str = "\n\n", separators: Optional[list[str]] = None, **kwargs: Any):
        """Create a new TextSplitter."""
        super().__init__(**kwargs)
        self._fixed_separator = fixed_separator
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """Split incoming text and return chunks."""
        if self._fixed_separator:
            chunks = text.split(self._fixed_separator)
        else:
            chunks = [text]

        final_chunks = []
        for chunk in chunks:
            if self._length_function(chunk) > self._chunk_size:
                final_chunks.extend(self.recursive_split_text(chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks

    def recursive_split_text(self, text: str) -> list[str]:
        """Split incoming text and return chunks."""
        final_chunks = []
        # Get appropriate separator to use
        separator = self._separators[-1]
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                break
        # Now that we have the separator, split the text
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        # Now go merging things, recursively splitting longer texts.
        _good_splits = []
        _good_splits_lengths = []  # cache the lengths of the splits
        for s in splits:
            s_len = self._length_function(s)
            if s_len < self._chunk_size:
                _good_splits.append(s)
                _good_splits_lengths.append(s_len)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, separator, _good_splits_lengths)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                    _good_splits_lengths = []
                other_info = self.recursive_split_text(s)
                final_chunks.extend(other_info)
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, separator, _good_splits_lengths)
            final_chunks.extend(merged_text)
        return final_chunks


def convert_nodes_to_documents(nodes: List[BaseNode]) -> Sequence[Document]:
    """
    将 BaseNode 对象转换为 Document 对象。

    参数:
        nodes (List[BaseNode]): 需要转换的 BaseNode 列表。

    返回:
        Sequence[Document]: 转换后的 Document 对象列表。
    """
    return [Document(text=node.text, metadata=node.metadata) for node in nodes]


def nodes_to_chunks_with_metadata(nodes: List[BaseNode]) -> List[str]:
    """
    将 BaseNode 的 text 和 metadata 拼成一个 chunk，并返回 list[str]。

    参数:
        nodes (List[BaseNode]): 需要处理的 BaseNode 列表。

    返回:
        List[str]: 每个 node 的 text 和 metadata 组成的字符串列表。
    """
    chunks = []
    for node in nodes:
        # 将 metadata 转换为字符串
        metadata_str = " | ".join([f"{key}: {value}" for key, value in node.metadata.items()])
        # 拼接 text 和 metadata
        chunk = f"{node.text}\n\n来源: {metadata_str}"
        chunks.append(chunk)
    return chunks


class MarkdownTextSplitter(EnhanceRecursiveCharacterTextSplitter):
    def __init__(self, fixed_separator: str = "\n\n", separators: Optional[list[str]] = None, **kwargs: Any):
        """
        Create a new MarkdownTextSplitter, inheriting from EnhanceRecursiveCharacterTextSplitter.
        Args:
            fixed_separator: The fixed separator to use for splitting. Defaults to "\n\n" (paragraph break).
            separators: List of other separators to try for splitting (e.g., newlines, spaces).
        """
        super().__init__(**kwargs)
        self._fixed_separator = fixed_separator
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._md_node_parser = MarkdownNodeParser()
        self._simple_chunk_parser = SimpleNodeParser(
            chunk_size=kwargs.get("chunk_size"), chunk_overlap=kwargs.get("chunk_overlap")
        )

    def split_text(self, text: str):
        # chunks = self._spliter.split_text(text=text)
        document = Document(text=text)
        markdown_nodes = self._md_node_parser.get_nodes_from_documents(documents=[document])

        simple_nodes = convert_nodes_to_documents(markdown_nodes)
        nodes = self._simple_chunk_parser.get_nodes_from_documents(simple_nodes)

        return nodes_to_chunks_with_metadata(nodes=nodes)