# -*- coding: UTF-8 -*-
"""
@Project : api
@File    : __init__.py.py
@Author  : yanglh
@Data    : 2025/4/16 16:18
"""

from flask import Blueprint
from flask_restful import Api  # type: ignore

bp = Blueprint("remote_api", __name__, url_prefix="/remote-api")
api: Api = Api(bp)

# 导入API模块
from controllers.remote_api.files import RemoteUploadFileApi
