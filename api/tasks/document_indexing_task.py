import datetime
import logging
import time
from typing import Any

import click
from celery import shared_task  # type: ignore

from configs import dify_config
from core.indexing_runner import DocumentIsPausedError, IndexingRunner
from extensions.ext_database import db
from models.dataset import Dataset, Document
from services.entities.knowledge_entities.knowledge_entities import SplitStrategy
from services.feature_service import FeatureService


@shared_task(queue="dataset")
def document_indexing_task(dataset_id: str, document_ids: list, split_strategy_dict: dict):
    """
    Async process document
    :param dataset_id:
    :param document_ids:
    :param split_strategy_dict: serialized split_strategy dict

    Usage: document_indexing_task.delay(dataset_id, document_ids, split_strategy_dict)
    """
    logging.info(
        click.style(
            "task params:{}, document_ids:{}, split:{}".format(dataset_id, document_ids, split_strategy_dict),
            fg="yellow",
        )
    )
    # 从字典重构 SplitStrategy 对象
    split_strategy = SplitStrategy(**split_strategy_dict) if split_strategy_dict else None

    documents = []
    start_at = time.perf_counter()
    dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        logging.info(click.style("Dataset is not found: {}".format(dataset_id), fg="yellow"))
        db.session.close()
        return
    # check document limit
    features = FeatureService.get_features(dataset.tenant_id)
    try:
        if features.billing.enabled:
            vector_space = features.vector_space
            count = len(document_ids)
            batch_upload_limit = int(dify_config.BATCH_UPLOAD_LIMIT)
            if features.billing.subscription.plan == "sandbox" and count > 1:
                raise ValueError("Your current plan does not support batch upload, please upgrade your plan.")
            if count > batch_upload_limit:
                raise ValueError(f"You have reached the batch upload limit of {batch_upload_limit}.")
            if 0 < vector_space.limit <= vector_space.size:
                raise ValueError(
                    "Your total number of documents plus the number of uploads have over the limit of "
                    "your subscription."
                )
    except Exception as e:
        for document_id in document_ids:
            document = (
                db.session.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()
            )
            if document:
                document.indexing_status = "error"
                document.error = str(e)
                document.stopped_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                db.session.add(document)
        db.session.commit()
        db.session.close()
        return

    for document_id in document_ids:
        logging.info(click.style("Start process document: {}".format(document_id), fg="green"))

        document = (
            db.session.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()
        )

        if document:
            document.indexing_status = "parsing"
            document.processing_started_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            documents.append(document)
            db.session.add(document)
    db.session.commit()

    index_processor_config: dict[str, Any] = {}
    # 如果外置策略存在，则设置外置切分策略server地址
    if split_strategy and split_strategy.external_strategy_desc:
        index_processor_config["server_address"] = split_strategy.external_strategy_desc.url
        logging.info(
            click.style(
                "documents: {} split strategy config: {}".format(document_ids, index_processor_config), fg="green"
            )
        )
    try:
        indexing_runner = IndexingRunner()
        indexing_runner.run(documents, index_processor_config)
        end_at = time.perf_counter()
        logging.info(click.style("Processed dataset: {} latency: {}".format(dataset_id, end_at - start_at), fg="green"))
    except DocumentIsPausedError as ex:
        logging.info(click.style(str(ex), fg="yellow"))
    except Exception:
        pass
    finally:
        db.session.close()
