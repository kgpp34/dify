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

        # Precompile regex patterns for headers of levels 1 to 6
        self.header_patterns = [re.compile(f'^{"#" * (i + 1)}\\s+(.*)', re.MULTILINE) for i in range(6)]
        self.code_block_placeholder = "CODE_BLOCK_{}"
        self.code_blocks = []

    def split_text(self, text):
        # Step 1: Replace code blocks with placeholders
        text_with_placeholders, self.code_blocks = self._replace_code_blocks(text)

        # Step 2: Split the text into chunks
        chunks = self._split_text(text_with_placeholders)

        # Step 3: Replace placeholders back with original code blocks
        chunks_with_code = [self._restore_code_blocks(chunk) for chunk in chunks]

        return chunks_with_code

    def _split_text(self, text, current_level=0):
        if current_level >= 6:
            return self._split_content_into_chunks(text)

        pattern = self.header_patterns[current_level]
        matches = list(pattern.finditer(text))
        chunks = []
        prev_end = 0
        for i, match in enumerate(matches):
            start = match.start()
            end = match.end()
            header = match.group(1)
            full_header = f'{"#" * (current_level + 1)} {header}'
            content_start = end
            if i + 1 < len(matches):
                next_start = matches[i + 1].start()
                content = text[content_start:next_start].lstrip()
            else:
                content = text[content_start:].lstrip()
            # Process content based on next level headers
            sub_chunks = self._split_text(content, current_level + 1)
            if sub_chunks:
                for sub_chunk in sub_chunks:
                    chunk = f"{full_header}\n\n{sub_chunk}"
                    if len(chunk) > self._chunk_size:
                        chunks.extend(self._split_large_chunk(chunk))
                    else:
                        chunks.append(chunk)
            else:
                content_chunks = self._split_content_into_chunks(f"{full_header}\n\n{content}")
                chunks.extend(content_chunks)
            prev_end = end
        if not matches:
            content_chunks = self._split_content_into_chunks(text)
            chunks.extend(content_chunks)
        return chunks

    def _split_content_into_chunks(self, content):
        chunks = []
        while len(content) > self._chunk_size:
            chunk = content[:self._chunk_size]
            last_newline = chunk.rfind('\n')
            if last_newline != -1:
                chunk = content[:last_newline]
                content = content[last_newline:].lstrip()
            else:
                chunk = content[:self._chunk_size]
                content = content[self._chunk_size:].lstrip()
            chunks.append(chunk)
        if content:
            chunks.append(content)
        return chunks

    def _split_large_chunk(self, chunk):
        # Split large chunks while preserving headers
        # Implement logic to split the chunk into smaller parts
        # Ensure each part starts with the appropriate header
        # This is a placeholder for the actual splitting logic
        return [chunk]

    def _replace_code_blocks(self, text):
        # Replace indented code blocks
        indented_code_pattern = re.compile(r'^ {4}(.*?)(?=\n{2,}|$)', re.MULTILINE | re.DOTALL)
        indented_codes = indented_code_pattern.findall(text)
        for i, code in enumerate(indented_codes):
            placeholder = self.code_block_placeholder.format(i)
            text = re.sub(re.escape(code), placeholder, text, 1)
            self.code_blocks.append(code)

        # Replace fenced code blocks
        fenced_code_pattern = re.compile(r'```.*?```', re.DOTALL)
        fenced_codes = fenced_code_pattern.findall(text)
        for i, code in enumerate(fenced_codes):
            placeholder = self.code_block_placeholder.format(len(self.code_blocks) + i)
            text = re.sub(re.escape(code), placeholder, text, 1)
            self.code_blocks.append(code)

        return text, self.code_blocks

    def _restore_code_blocks(self, chunk):
        for i, code in enumerate(self.code_blocks):
            placeholder = self.code_block_placeholder.format(i)
            chunk = chunk.replace(placeholder, code)
        return chunk

