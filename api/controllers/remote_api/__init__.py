# -*- coding: UTF-8 -*-
"""
@Project : api
@File    : __init__.py.py
@Author  : yanglh
@Data    : 2025/4/16 16:18
"""

from flask import Blueprint
from flask_restful import Api  # type: ignore  # 添加类型忽略注释

bp = Blueprint("remote_api", __name__, url_prefix="/remote-api")
api: Api = Api(bp)  # 添加类型注解

# 在这里导入路由，确保它们在蓝图创建后注册
# 明确导入需要的类，而不是使用 import *
from controllers.remote_api.files import RemoteUploadFileApi  # 明确导入类
