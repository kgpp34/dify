#!/usr/bin/env python3
import os
import re
from pathlib import Path


def patch_sqlalchemy():
    """为 SQLAlchemy 添加 Kingbase 支持"""
    try:
        # 获取虚拟环境路径
        venv_path = os.environ.get("VIRTUAL_ENV", "/app/api/.venv")
        base_file = (
            Path(venv_path)
            / "lib"
            / "python3.12"
            / "site-packages"
            / "sqlalchemy"
            / "dialects"
            / "postgresql"
            / "base.py"
        )

        if not base_file.exists():
            print(f"SQLAlchemy base.py not found at {base_file}")
            return False

        content = base_file.read_text()

        # 检查是否已经打过补丁
        if "Kingbase" in content:
            print("SQLAlchemy already patched for Kingbase")
            return True

        # 找到 _get_server_version_info 方法并替换
        pattern = r"def _get_server_version_info\(self, connection\):.*?return tuple\([^)]+\)"

        replacement = """def _get_server_version_info(self, connection):
        v = connection.exec_driver_sql("select pg_catalog.version()").scalar()
        
        # 支持 Kingbase 版本解析
        m = re.match(
            r".*(?:Kingbase|KingbaseES)\\s*"
            r"V(\\d{3})R(\\d{3})C(\\d{3})",
            v,
        )
        
        if m:
            major = int(m.group(1))
            minor = int(m.group(2))
            patch = int(m.group(3))
            return (major, minor, patch)
        
        # 原始 PostgreSQL 解析逻辑
        m = re.match(
            r".*(?:PostgreSQL|EnterpriseDB) "
            r"(\\d+)\\.?(\\d+)?(?:\\.(\\d+))?(?:\\.\\d+)?(?:devel|beta)?",
            v,
        )
        
        if not m:
            raise AssertionError(f"Could not determine version from string '{v}'")
        
        return tuple([int(x) for x in m.group(1, 2, 3) if x is not None])"""

        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        if new_content != content:
            base_file.write_text(new_content)
            print("SQLAlchemy successfully patched for Kingbase support")
            return True
        else:
            print("Failed to patch SQLAlchemy - pattern not found")
            return False

    except Exception as e:
        print(f"Error patching SQLAlchemy: {e}")
        return False


if __name__ == "__main__":
    success = patch_sqlalchemy()
    exit(0 if success else 1)
