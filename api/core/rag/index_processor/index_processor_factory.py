"""Abstract interface for document loader implementations."""

from typing import Any, Optional

from core.rag.index_processor.constant.index_type import IndexType
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.index_processor.processor.external_index_processor import ExternalIndexProcessor
from core.rag.index_processor.processor.paragraph_index_processor import ParagraphIndexProcessor
from core.rag.index_processor.processor.parent_child_index_processor import ParentChildIndexProcessor
from core.rag.index_processor.processor.qa_index_processor import QAIndexProcessor


class IndexProcessorFactory:
    """IndexProcessorInit."""

    def __init__(
        self, index_type: str | None, config_options: Optional[dict[str, Any]] = None, clean: Optional[bool] = False
    ):
        """
        初始化索引处理器工厂。

        Args:
            index_type: 索引类型
            config_options: 配置选项，可包含如下字段：
                - server_address: 自定义处理器服务地址（用于CustomIndexProcessor）
            clean: 是否是clean index processor
        """
        self._index_type = index_type
        self._config_options = config_options or {}
        self._clean_flag = clean or False

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
            server_address: str | None = None
            # validate server address
            if self._clean_flag is False or self._clean_flag is None:
                server_address = self._config_options.get("server_address")
                if not server_address:
                    raise ValueError("External Split Strategy API Endpoint must be not null.")

            # 确保 server_address 不为 None
            if server_address is None:
                # 为 clean 模式提供默认值或抛出异常
                raise ValueError("Server address is required for ExternalIndexProcessor")

            return ExternalIndexProcessor(server_address=server_address)

        else:
            raise ValueError(f"Index type {self._index_type} is not supported.")
