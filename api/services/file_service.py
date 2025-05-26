import datetime
import hashlib
import logging
import os
import uuid
from typing import Any, Literal, Union

from flask_login import current_user  # type: ignore
from werkzeug.exceptions import NotFound

from configs import dify_config
from constants import (
    AUDIO_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from core.file import helpers as file_helpers
from core.rag.extractor.extract_processor import ExtractProcessor
from extensions.ext_database import db
from extensions.ext_storage import storage
from models.account import Account
from models.enums import CreatedByRole
from models.model import EndUser, UploadFile

from .errors.file import FileTooLargeError, UnsupportedFileTypeError

PREVIEW_WORDS_LIMIT = 3000

logger = logging.getLogger(__name__)


class FileService:
    @staticmethod
    def upload_file(
        *,
        filename: str,
        content: bytes,
        mimetype: str,
        user: Union[Account, EndUser, Any],
        source: Literal["datasets"] | None = None,
        source_url: str = "",
    ) -> UploadFile:
        # get file extension
        extension = os.path.splitext(filename)[1].lstrip(".").lower()

        # check if filename contains invalid characters
        if any(c in filename for c in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]):
            raise ValueError("Filename contains invalid characters")

        if len(filename) > 200:
            filename = filename.split(".")[0][:200] + "." + extension

        if source == "datasets" and extension not in DOCUMENT_EXTENSIONS:
            raise UnsupportedFileTypeError()

        # get file size
        file_size = len(content)

        # check if the file size is exceeded
        if not FileService.is_file_size_within_limit(extension=extension, file_size=file_size):
            raise FileTooLargeError

        # generate file key
        file_uuid = str(uuid.uuid4())

        if isinstance(user, Account):
            current_tenant_id = user.current_tenant_id
        else:
            # end_user
            current_tenant_id = user.tenant_id

        file_key = "upload_files/" + (current_tenant_id or "") + "/" + file_uuid + "." + extension

        # save file to storage
        storage.save(file_key, content)

        # save file to db
        upload_file = UploadFile(
            tenant_id=current_tenant_id or "",
            storage_type=dify_config.STORAGE_TYPE,
            key=file_key,
            name=filename,
            size=file_size,
            extension=extension,
            mime_type=mimetype,
            created_by_role=(CreatedByRole.ACCOUNT if isinstance(user, Account) else CreatedByRole.END_USER),
            created_by=user.id,
            created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            used=False,
            hash=hashlib.sha3_256(content).hexdigest(),
            source_url=source_url,
        )

        db.session.add(upload_file)
        db.session.commit()

        if not upload_file.source_url:
            upload_file.source_url = file_helpers.get_signed_file_url(upload_file_id=upload_file.id)
            db.session.add(upload_file)
            db.session.commit()

        return upload_file

    @staticmethod
    def is_file_size_within_limit(*, extension: str, file_size: int) -> bool:
        if extension in IMAGE_EXTENSIONS:
            file_size_limit = dify_config.UPLOAD_IMAGE_FILE_SIZE_LIMIT * 1024 * 1024
        elif extension in VIDEO_EXTENSIONS:
            file_size_limit = dify_config.UPLOAD_VIDEO_FILE_SIZE_LIMIT * 1024 * 1024
        elif extension in AUDIO_EXTENSIONS:
            file_size_limit = dify_config.UPLOAD_AUDIO_FILE_SIZE_LIMIT * 1024 * 1024
        else:
            file_size_limit = dify_config.UPLOAD_FILE_SIZE_LIMIT * 1024 * 1024

        return file_size <= file_size_limit

    @staticmethod
    def upload_text(text: str, text_name: str) -> UploadFile:
        if len(text_name) > 200:
            text_name = text_name[:200]
        # user uuid as file name
        file_uuid = str(uuid.uuid4())
        file_key = "upload_files/" + current_user.current_tenant_id + "/" + file_uuid + ".txt"

        # save file to storage
        storage.save(file_key, text.encode("utf-8"))

        # save file to db
        upload_file = UploadFile(
            tenant_id=current_user.current_tenant_id,
            storage_type=dify_config.STORAGE_TYPE,
            key=file_key,
            name=text_name,
            size=len(text),
            extension="txt",
            mime_type="text/plain",
            created_by=current_user.id,
            created_by_role=CreatedByRole.ACCOUNT,
            created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            used=True,
            used_by=current_user.id,
            used_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )

        db.session.add(upload_file)
        db.session.commit()

        return upload_file

    @staticmethod
    def get_file_preview(file_id: str):
        upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_id).first()

        if not upload_file:
            raise NotFound("File not found")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in DOCUMENT_EXTENSIONS:
            raise UnsupportedFileTypeError()

        text = ExtractProcessor.load_from_upload_file(upload_file, return_text=True)
        text = text[0:PREVIEW_WORDS_LIMIT] if text else ""

        return text

    @staticmethod
    def get_image_preview(file_id: str, timestamp: str, nonce: str, sign: str):
        result = file_helpers.verify_image_signature(
            upload_file_id=file_id, timestamp=timestamp, nonce=nonce, sign=sign
        )
        if not result:
            raise NotFound("File not found or signature is invalid")

        upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_id).first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        generator = storage.load(upload_file.key, stream=True)

        return generator, upload_file.mime_type

    @staticmethod
    def get_file_generator_by_file_id(file_id: str, timestamp: str, nonce: str, sign: str):
        result = file_helpers.verify_file_signature(upload_file_id=file_id, timestamp=timestamp, nonce=nonce, sign=sign)
        if not result:
            raise NotFound("File not found or signature is invalid")

        upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_id).first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        generator = storage.load(upload_file.key, stream=True)

        return generator, upload_file

    @staticmethod
    def get_public_image_preview(file_id: str):
        upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_id).first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        generator = storage.load(upload_file.key)

        return generator, upload_file.mime_type

    @staticmethod
    def get_unused_files_by_tenant_and_user(tenant_id: str, user_id: str):
        """
        获取指定租户和用户创建的未使用文件列表

        Args:
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            未使用的文件列表
        """
        unused_files = (
            db.session.query(UploadFile)
            .filter(UploadFile.tenant_id == tenant_id, UploadFile.created_by == user_id, UploadFile.used == False)
            .all()
        )

        return unused_files

    @staticmethod
    def mark_file_used(file_ids: list[str]):
        if file_ids is not None and len(file_ids) > 0:
            file_details = (
                db.session.query(UploadFile)
                .filter(UploadFile.tenant_id == current_user.current_tenant_id, UploadFile.id.in_(file_ids))
                .all()
            )

            # mark file used
            for file in file_details:
                file.used = True

            db.session.commit()

    @staticmethod
    def delete_file(file_id: str):
        """
        删除指定 ID 的文件记录及其在存储中的文件。

        首先检查文件是否可以删除，然后将实际删除操作提交到异步任务队列中执行。

        Args:
            file_id: 要删除的文件 ID

        Raises:
            NotFound: 如果文件未找到
            ValueError: 如果文件已被使用
        """

        upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_id).first()

        if not upload_file:
            raise NotFound("File not found")

        # 检查文件是否已被使用
        if upload_file.used:
            raise ValueError("Cannot delete file that is in use")

        # 重新查询文件记录，确保获取最新状态
        logger.info(f"查询到即将删除的文件: {file_id}")

        if not upload_file:
            logger.warning(f"文件不存在，无法删除: {file_id}")
            return

        # 从存储中删除文件
        try:
            storage.delete(upload_file.key)
        except Exception as e:
            logger.exception(f"从存储中删除文件失败 {upload_file.key}")
            raise e
            # 即使存储删除失败，也继续删除数据库记录

        # 从数据库中删除记录
        db.session.delete(upload_file)
        db.session.commit()

        logger.info(f"成功删除文件: {file_id}")

        return True
