"""Functionality for splitting text."""

from __future__ import annotations

import re
from typing import Any, Optional

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

        self._h1_pattern = re.compile(r"^#\s+([^\n]+)", re.MULTILINE)
        self._header_pattern = re.compile(r"^(#{1,6})\s+([^\n]+)", re.MULTILINE)

    def split_text(self, text: str) -> list[str]:
        """Split Markdown text into chunks based on header hierarchy"""
        # 1. 首先按一级标题分割
        h1_sections = self._split_by_h1(text)

        final_chunks = []
        for title, content in h1_sections:
            if not content.strip():
                continue

            # 2. 智能处理每个一级标题下的内容
            section_chunks = self._process_section(title, content)
            final_chunks.extend(section_chunks)

        # 3. 清理所有chunk中的特殊字符
        final_chunks = [self._clean_chunk(chunk) for chunk in final_chunks]

        return final_chunks

    def _split_by_h1(self, text: str) -> list[tuple[str, str]]:
        """Split text by h1 headers"""
        sections = []
        matches = list(self._h1_pattern.finditer(text))

        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            title = matches[i].group(1)
            content = text[start:end]
            sections.append((title.strip(), content))

        return sections

    def _process_section(self, h1_title: str, content: str) -> list[str]:
        """Process content under each h1 header intelligently"""
        # 获取所有子标题及其内容
        subsections = self._get_subsections(content)
        if not subsections:
            return [self._create_chunk(h1_title, "", content)]

        chunks = []
        current_chunk = []
        current_size = 0
        current_header = None

        for header_level, header_text, section_content in subsections:
            section_size = self._length_function(section_content)

            # 是否应该开始新的chunk
            should_start_new_chunk = (
                current_size + section_size > self._chunk_size * 1.2  # 超过阈值
                or header_level <= 3  # 较高层级的标题强制分割
            )

            if should_start_new_chunk and current_chunk:
                # 合并当前chunk并添加到结果中
                chunk_content = self._merge_subsections(current_chunk)
                chunks.append(self._create_chunk(h1_title, current_header, chunk_content))
                current_chunk = []
                current_size = 0

            # 如果单个章节超过chunk_size，需要进一步分割
            if section_size > self._chunk_size:
                split_chunks = self._split_long_section(h1_title, header_text, header_level, section_content)
                chunks.extend(split_chunks)
            else:
                if not current_chunk:
                    current_header = f"{'#' * header_level} {header_text}"
                current_chunk.append((header_level, header_text, section_content))
                current_size += section_size

        # 处理最后的chunk
        if current_chunk:
            chunk_content = self._merge_subsections(current_chunk)
            chunks.append(self._create_chunk(h1_title, current_header, chunk_content))

        return chunks

    def _get_subsections(self, content: str) -> list[tuple[int, str, str]]:
        """Extract all subsections with their headers"""
        matches = list(self._header_pattern.finditer(content))
        if not matches:
            return []

        subsections = []
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            level = len(matches[i].group(1))
            header = matches[i].group(2)
            section_content = content[start:end]
            subsections.append((level, header, section_content))

        return subsections

    def _split_long_section(self, h1_title: str, header_text: str, header_level: int, content: str) -> list[str]:
        """Split a long section into multiple chunks"""
        # 按段落分割
        paragraphs = content.split("\n\n")
        chunks = []
        current_paragraphs = []
        current_size = 0

        for para in paragraphs:
            para_size = self._length_function(para)
            if current_size + para_size > self._chunk_size:
                if current_paragraphs:
                    chunk_content = " ".join(current_paragraphs)
                    chunks.append(
                        self._create_chunk(
                            h1_title, f"{'#' * header_level} {header_text}", chunk_content, f"Part {len(chunks) + 1}"
                        )
                    )
                current_paragraphs = [para]
                current_size = para_size
            else:
                current_paragraphs.append(para)
                current_size += para_size

        if current_paragraphs:
            chunk_content = " ".join(current_paragraphs)
            chunks.append(
                self._create_chunk(
                    h1_title, f"{'#' * header_level} {header_text}", chunk_content, f"Part {len(chunks) + 1}"
                )
            )

        # 添加总部分数
        chunks = [chunk.replace("Part ", f"Part {i + 1} of {len(chunks)} - ") for i, chunk in enumerate(chunks)]

        return chunks

    def _merge_subsections(self, subsections: list[tuple[int, str, str]]) -> str:
        """Merge subsections into a single chunk"""
        merged = []
        for level, header, content in subsections:
            merged.append(f"{'#' * level} {header}")
            merged.append(content.strip())
        return " ".join(merged)

    def _create_chunk(self, h1_title: str, current_header: str, content: str, part_info: str = "") -> str:
        """Create a chunk with proper header information"""
        if part_info:
            return f"# {h1_title} {current_header} {part_info} {content}"
        return f"# {h1_title} {current_header} {content}"

    def _clean_chunk(self, text: str) -> str:
        """Clean special characters from chunk"""
        # 将多个空格替换为单个空格
        text = re.sub(r"\s+", " ", text)
        # 确保标题标记后有空格
        text = re.sub(r"(#{1,6})([^\s])", r"\1 \2", text)
        return text.strip()
