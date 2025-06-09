import re
from typing import Any

from sqlalchemy.dialects.postgresql import base


class KingbasePGDialect(base.PGDialect):
    """支持 Kingbase 的 PostgreSQL Dialect"""

    def _get_server_version_info(self, connection: Any) -> tuple[int, ...]:
        """修改后的版本信息获取方法，支持 PostgreSQL 和 Kingbase"""
        v = connection.exec_driver_sql("select pg_catalog.version()").scalar()

        # 首先尝试匹配 Kingbase
        m = re.match(
            r".*(?:Kingbase|KingbaseES)\s*"
            r"V(\d+)\D?(\d+)\D?(?:(\d+))?",
            v,
        )

        if m:
            return tuple([int(x) for x in m.group(1, 2, 3) if x is not None])

        # 如果不是 Kingbase，尝试匹配 PostgreSQL
        m = re.match(
            r".*(?:PostgreSQL|EnterpriseDB) "
            r"(\d+)\.?(\d+)?(?:\.(\d+))?(?:\.\d+)?(?:devel|beta)?",
            v,
        )

        if not m:
            raise AssertionError(f"Could not determine version from string '{v}'")

        return tuple([int(x) for x in m.group(1, 2, 3) if x is not None])


# 替换原始的 PGDialect
base.PGDialect = KingbasePGDialect  # type: ignore[misc]
