from urllib.parse import quote

from flask import Response
from werkzeug.exceptions import NotFound

from controllers.service_api import api
from controllers.service_api.wraps import (
    DatasetApiResource,
)
from core.file import helpers as file_helpers
from extensions.ext_database import db
from extensions.ext_storage import storage
from models.dataset import Dataset
from models.model import UploadFile
from services.dataset_service import DocumentService


def _get_document_upload_file(tenant_id: str, dataset_id: str, document_id: str) -> UploadFile:
    """Resolve the UploadFile backing a document, raising if dataset/document/file are missing or unsupported."""
    dataset_id = str(dataset_id)
    tenant_id = str(tenant_id)
    dataset = db.session.query(Dataset).filter(Dataset.tenant_id == tenant_id, Dataset.id == dataset_id).first()
    if not dataset:
        raise NotFound("Dataset not found.")

    document_id = str(document_id)
    document = DocumentService.get_document(dataset.id, document_id)
    if not document:
        raise NotFound("Document not found.")

    if document.data_source_type != "upload_file":
        raise ValueError(f"Document data source type ({document.data_source_type}) is not upload_file.")
    data_source_info = document.data_source_info_dict
    if not data_source_info or "upload_file_id" not in data_source_info:
        raise ValueError("Upload file id not found in document data source info.")

    upload_file = db.session.query(UploadFile).filter(UploadFile.id == data_source_info["upload_file_id"]).first()
    if not upload_file:
        raise NotFound("UploadFile not found.")
    return upload_file


class UploadFileApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id, document_id):
        """Get upload file."""
        upload_file = _get_document_upload_file(tenant_id, dataset_id, document_id)

        url = file_helpers.get_signed_file_url(upload_file_id=upload_file.id)
        return {
            "id": upload_file.id,
            "name": upload_file.name,
            "size": upload_file.size,
            "extension": upload_file.extension,
            "url": url,
            "download_url": f"{url}&as_attachment=true",
            "mime_type": upload_file.mime_type,
            "created_by": upload_file.created_by,
            "created_at": upload_file.created_at.timestamp(),
        }, 200


class DocumentDownloadApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id, document_id):
        """Download the original source file of a document."""
        upload_file = _get_document_upload_file(tenant_id, dataset_id, document_id)

        generator = storage.load(upload_file.key, stream=True)
        response = Response(generator, mimetype=upload_file.mime_type, direct_passthrough=True)
        if upload_file.size > 0:
            response.headers["Content-Length"] = str(upload_file.size)
        encoded_filename = quote(upload_file.name)
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-Type"] = "application/octet-stream"
        return response


api.add_resource(UploadFileApi, "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/upload-file")
api.add_resource(DocumentDownloadApi, "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/download")
