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

    def split_text(self, text: str) -> list[str]:
        """
        First split the text based on headings, then recursively split each chunk based on length.
        """
        # Step 1: Split by Markdown headers (titles)
        chunks = self._split_by_headings(text)

        # Step 2: Recursively split the chunks by length
        final_chunks = []
        for chunk in chunks:
            if self._length_function(chunk) > self._chunk_size:
                final_chunks.extend(self._recursive_split(chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks

    def _split_by_headings(self, text: str) -> list[str]:
        """
        Split the text by Markdown headers (e.g., #, ##, ###).
        """
        # Match Markdown headers (e.g., # Heading, ## Subheading)
        header_pattern = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)
        chunks = []
        last_index = 0

        # Iterate over the text and split it at each header
        for match in header_pattern.finditer(text):
            header = match.group(0)
            header_start = match.start()

            if last_index < header_start:
                chunks.append(self._clean_text(text[last_index:header_start].strip()))  # Clean the chunk

            chunks.append(self._clean_text(header))  # Clean the header itself
            last_index = match.end()

        # Add any remaining text after the last header
        if last_index < len(text):
            chunks.append(self._clean_text(text[last_index:].strip()))

        return chunks

    def _recursive_split(self, text: str) -> list[str]:
        """
        Recursively split longer text chunks, based on Markdown elements like paragraphs.
        """
        final_chunks = []

        # If the text is too long, split it further
        if self._length_function(text) > self._chunk_size:
            # Split based on available separators (e.g., paragraphs or newlines)
            for separator in self._separators:
                if separator in text:
                    chunks = text.split(separator)
                    for chunk in chunks:
                        if chunk.strip():  # Ignore empty chunks
                            final_chunks.append(self._clean_text(chunk.strip()))  # Clean each chunk
                    break
            else:
                # If no separators found, split by lines
                final_chunks.extend(self._clean_text(line.strip()) for line in text.split("\n"))
        else:
            final_chunks.append(self._clean_text(text))

        return final_chunks

    def _clean_text(self, text: str) -> str:
        """
        Clean text by removing unnecessary spaces, empty lines, and special characters.
        """
        # Remove extra spaces, tabs, and newlines
        text = re.sub(r'\s+', ' ', text)  # Collapse multiple spaces/tabs into a single space
        text = re.sub(r'\n+', '\n', text)  # Collapse multiple newlines into a single newline
        text = text.strip()  # Remove leading/trailing whitespace

        # Optional: Remove specific unwanted characters (like extra Markdown formatting)
        text = re.sub(r'^\s*(#.*)', r'\1', text)  # Ensure headers are properly formatted (e.g., no leading spaces)

        return text
