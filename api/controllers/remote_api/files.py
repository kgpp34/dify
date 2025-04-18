from flask import request
from flask_restful import Resource, marshal_with  # type: ignore
from werkzeug.exceptions import Forbidden

import services
from controllers.files.error import UnsupportedFileTypeError
from controllers.inner_api.plugin.wraps import get_user
from controllers.remote_api import api  # 这里导入的api需要有明确的类型
from controllers.service_api.app.error import FileTooLargeError
from fields.file_fields import file_fields
from services.file_service import FileService


class RemoteUploadFileApi(Resource):
    @marshal_with(file_fields)
    def post(self):
        # 从请求中获取文件
        file = request.files["file"]
        tenant_id = request.args.get("tenant_id")

        if not tenant_id:
            raise Forbidden("无效请求：缺少租户ID")

        user_id = request.args.get("user_id")
        user = get_user(tenant_id, user_id)

        filename = file.filename
        mimetype = file.mimetype

        if not filename or not mimetype:
            raise Forbidden("无效请求：文件名或MIME类型缺失")

        try:
            upload_file = FileService.upload_file(
                filename=filename,
                content=file.read(),
                mimetype=mimetype,
                user=user,
                source=None,
            )
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return upload_file, 201


# 注册API路由
api.add_resource(RemoteUploadFileApi, "/files/upload")
