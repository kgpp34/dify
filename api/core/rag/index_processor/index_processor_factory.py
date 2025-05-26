"""Abstract interface for document loader implementations."""

from typing import Any, Optional

from core.rag.index_processor.constant.index_type import IndexType
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.index_processor.processor.custom_index_processor import CustomParagraphIndexProcessor
from core.rag.index_processor.processor.paragraph_index_processor import ParagraphIndexProcessor
from core.rag.index_processor.processor.parent_child_index_processor import ParentChildIndexProcessor
from core.rag.index_processor.processor.qa_index_processor import QAIndexProcessor
from core.rag.index_processor.processor.external_index_processor import ExternalIndexProcessor


class IndexProcessorFactory:
    """IndexProcessorInit."""

    def __init__(self, index_type: str | None, config_options: Optional[dict[str, Any]] = None):
        """
        初始化索引处理器工厂。

        Args:
            index_type: 索引类型
            config_options: 配置选项，可包含如下字段：
                - server_address: 自定义处理器服务地址（用于CustomIndexProcessor）
        """
        self._index_type = index_type
        self._config_options = config_options or {}

    def init_index_processor(self) -> BaseIndexProcessor:
        """Init index processor."""

        if not self._index_type:
            raise ValueError("Index type must be specified.")

        if self._index_type == IndexType.PARAGRAPH_INDEX:
            return ParagraphIndexProcessor()
        elif self._index_type == IndexType.QA_INDEX:
            return QAIndexProcessor()
        elif self._index_type == IndexType.PARENT_CHILD_INDEX:
            return ParentChildIndexProcessor()
        elif self._index_type == IndexType.EXTERNAL_INDEX:
            server_address = self._config_options.get("server_address")
            api_key = self._config_options.get("api_key")
            if not server_address:
                raise ValueError("Server address must be not null.")
            return ExternalIndexProcessor(server_address=server_address, api_key=api_key)
        else:
            raise ValueError(f"Index type {self._index_type} is not supported.")
