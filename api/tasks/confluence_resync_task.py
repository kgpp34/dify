import hashlib
import logging

from celery import shared_task  # type: ignore

from libs.helper import ConfluenceFetcher, ConfluencePageInfo
from models.dataset import Document
from services.dataset_service import DocumentService
from services.file_service import FileService


class ConfluenceResyncTask:
    """定时检查 Confluence 页面是否更新，并上传文档的任务类"""

    def __init__(self):
        self.file_service = FileService()
        self.document_service = DocumentService()
        self.confluence_fetcher = ConfluenceFetcher()

    def resync(self, batch_size=100):
        """定时检查 Confluence 页面是否更新，并上传文档，支持批量处理"""
        documents = self.document_service.get_documents_with_metadata()
        logging.info("aaaaaaaaaaaaaaaaaaaa")
        total_documents = len(documents)
        logging.info(f"Total Confluence related documents: {total_documents}")

        # 按批次分批处理
        for batch_start in range(0, total_documents, batch_size):
            batch_documents = documents[batch_start : batch_start + batch_size]
            logging.info(f"Processing batch {batch_start // batch_size + 1} of {len(batch_documents)} documents.")

            # 提取所有 Confluence 相关文档的 page_id
            page_ids = [
                document.doc_metadata.get("page_id")
                for document in batch_documents
                if document.doc_metadata.get("page_id")
            ]

            if page_ids:
                # 使用批量方法获取多个 Confluence 页面内容
                pages_info = self.confluence_fetcher.fetch_confluence_page_by_ids(page_ids)

                for document, page_info in zip(batch_documents, pages_info):
                    if page_info and self.verify_confluence_page(document, page_info.content):
                        logging.info(f"Page {document.doc_metadata['page_id']} has been updated.")
                        # 获取历史的文件信息
                        last_file = self.file_service.get_file_by_file_id(document.tenant_id, document.file_id)
                        if not last_file:
                            logging.error("File associated with document not found.")
                        # 生成文件并上传
                        if last_file:
                            new_file = self.generate_custom_file(document, page_info)
                        if new_file:
                            # 更新文档的相关信息并删除历史file, 提交异步indexing任务
                            DocumentService.auto_update_document(new_file, document)
                            FileService.delete_file(last_file.id)

            logging.info(f"Batch {batch_start // batch_size + 1} processing completed.")

        logging.info("All Confluence related documents have been processed.")

    def verify_confluence_page(self, document, content) -> bool:
        """根据 hash 值判断 Confluence 页面是否更新"""
        content_hash = hashlib.sha3_256(content).hexdigest()  # 与UploadFile中的hash保持一致

        if document.doc_metadata.get("doc_hash") == content_hash:
            logging.info(f"Confluence page {document.doc_metadata['page_id']} has not been updated.")
            return False

        return True

    def generate_custom_file(self, document: Document, page_info: ConfluencePageInfo):
        """直接从上传的文件中获取相关字段并调用 upload_file 上传文件"""
        if not page_info:
            logging.error("No content available for generating the file.")
            return None

        # 获取上传的文件信息，假设文件已经保存到数据库中，并通过 document 获取
        last_file = self.file_service.get_file_by_file_id(document.tenant_id, document.file_id)
        if not last_file:
            logging.error("File associated with document not found.")
            return None

        try:
            # 调用 upload_file 上传文件
            new_file = FileService.upload_file(
                filename=last_file.filename,
                content=page_info.content.encode("utf-8"),
                mimetype=page_info.mimetype,
                user=last_file.current_user,
                source=last_file.source,
            )
        except Exception as e:
            logging.exception(f"Failed to upload new file for document {document.id}")
            return None

        return new_file


@shared_task(queue="dataset")
def resync_task(batch_size=100):
    logging.info("resync_task")
    task = ConfluenceResyncTask()
    task.resync(batch_size)
