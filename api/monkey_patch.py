import logging
import re
from typing import Any

from sqlalchemy.dialects.postgresql import base

# 设置日志
logger = logging.getLogger(__name__)


class KingbasePGDialect(base.PGDialect):
    """支持 Kingbase 的 PostgreSQL Dialect"""

    def _get_server_version_info(self, connection: Any) -> tuple[int, ...]:
        """修改后的版本信息获取方法，支持 PostgreSQL 和 Kingbase"""
        v = connection.exec_driver_sql("select pg_catalog.version()").scalar()
        logger.info(f"[KingbasePGDialect] 获取到数据库版本字符串: {v}")

        # 首先尝试匹配 Kingbase - 更新正则表达式以匹配实际格式
        # 格式: KingbaseES V008R006C007B0024PSC001
        m = re.match(
            r".*(?:Kingbase|KingbaseES)\s*"
            r"V(\d{3})R(\d{3})C(\d{3})",  # 匹配 V008R006C007 格式
            v,
        )

        if m:
            # 将 Kingbase 版本号转换为 PostgreSQL 兼容格式
            # V008R006C007 -> (8, 6, 7)
            major = int(m.group(1))
            minor = int(m.group(2))
            patch = int(m.group(3))
            version_tuple = (major, minor, patch)
            logger.info(f"[KingbasePGDialect] 检测到 Kingbase 数据库，版本: {version_tuple}")
            return version_tuple

        # 如果不是 Kingbase，尝试匹配 PostgreSQL
        logger.info("[KingbasePGDialect] 未匹配到 Kingbase，尝试 PostgreSQL 解析")
        m = re.match(
            r".*(?:PostgreSQL|EnterpriseDB) "
            r"(\d+)\.?(\d+)?(?:\.(\d+))?(?:\.\d+)?(?:devel|beta)?",
            v,
        )

        if not m:
            logger.error(f"[KingbasePGDialect] 无法解析版本字符串: '{v}'")
            raise AssertionError(f"Could not determine version from string '{v}'")

        # 确保始终返回三元组，缺失的版本号用0填充
        major = int(m.group(1)) if m.group(1) else 0
        minor = int(m.group(2)) if m.group(2) else 0
        patch = int(m.group(3)) if m.group(3) else 0
        version_tuple = (major, minor, patch)
        logger.info(f"[KingbasePGDialect] 检测到 PostgreSQL 数据库，版本: {version_tuple}")
        return version_tuple


# 替换原始的 PGDialect
logger.info("[KingbasePGDialect] 正在应用 Kingbase Dialect")
base.PGDialect = KingbasePGDialect  # type: ignore[misc]
logger.info("[KingbasePGDialect] Kingbase Dialect 已应用")
