from flask import request
from flask_restful import reqparse  # type: ignore
from werkzeug.exceptions import NotFound

from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource
from extensions.ext_database import db
from models.model import Tag, TagBinding
from services.dataset_service import DatasetService
from services.tag_service import TagService

KNOWLEDGE_TAG_TYPE = "knowledge"


def _validate_name(name: str) -> str:
    if not name or len(name) < 1 or len(name) > 50:
        raise ValueError("Name must be between 1 to 50 characters.")
    return name


def _get_knowledge_tag(tag_id: str, tenant_id: str) -> Tag:
    tag = (
        db.session.query(Tag)
        .filter(Tag.id == tag_id, Tag.tenant_id == tenant_id, Tag.type == KNOWLEDGE_TAG_TYPE)
        .first()
    )
    if tag is None:
        raise NotFound("Tag not found.")
    return tag


def _validate_knowledge_tag_ids(tag_ids: list[str], tenant_id: str) -> None:
    tags = (
        db.session.query(Tag.id)
        .filter(Tag.id.in_(tag_ids), Tag.tenant_id == tenant_id, Tag.type == KNOWLEDGE_TAG_TYPE)
        .all()
    )
    found_tag_ids = {str(tag.id) for tag in tags}
    if len(found_tag_ids) != len(set(tag_ids)):
        raise NotFound("Tag not found.")


def _ensure_dataset(dataset_id: str, tenant_id: str) -> None:
    dataset = DatasetService.get_dataset(dataset_id)
    if dataset is None or str(dataset.tenant_id) != tenant_id:
        raise NotFound("Dataset not found.")


def _serialize_tag(tag, binding_count: int | str | None = None) -> dict:
    resolved_binding_count = binding_count
    if resolved_binding_count is None:
        resolved_binding_count = getattr(tag, "binding_count", 0)

    return {
        "id": tag.id,
        "name": tag.name,
        "type": getattr(tag, "type", KNOWLEDGE_TAG_TYPE),
        "binding_count": str(resolved_binding_count or 0),
    }


class DatasetTagApi(DatasetApiResource):
    def get(self, tenant_id):
        keyword = request.args.get("keyword")
        tags = TagService.get_tags(KNOWLEDGE_TAG_TYPE, tenant_id, keyword)
        return [_serialize_tag(tag) for tag in tags], 200

    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "name",
            type=_validate_name,
            nullable=False,
            required=True,
            location="json",
            help="Name must be between 1 to 50 characters.",
        )
        args = parser.parse_args()

        tag = TagService.save_tags({"name": args["name"], "type": KNOWLEDGE_TAG_TYPE})
        return _serialize_tag(tag, binding_count=0), 200

    def patch(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "tag_id",
            type=str,
            nullable=False,
            required=True,
            location="json",
            help="Tag ID is required.",
        )
        parser.add_argument(
            "name",
            type=_validate_name,
            nullable=False,
            required=True,
            location="json",
            help="Name must be between 1 to 50 characters.",
        )
        args = parser.parse_args()

        tag = _get_knowledge_tag(args["tag_id"], tenant_id)
        tag.name = args["name"]
        db.session.commit()

        binding_count = (
            db.session.query(TagBinding)
            .filter(TagBinding.tag_id == args["tag_id"], TagBinding.tenant_id == tenant_id)
            .count()
        )
        return _serialize_tag(tag, binding_count=binding_count), 200

    def delete(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "tag_id",
            type=str,
            nullable=False,
            required=True,
            location="json",
            help="Tag ID is required.",
        )
        args = parser.parse_args()

        tag = _get_knowledge_tag(args["tag_id"], tenant_id)
        db.session.query(TagBinding).filter(
            TagBinding.tag_id == args["tag_id"],
            TagBinding.tenant_id == tenant_id,
        ).delete(synchronize_session=False)
        db.session.delete(tag)
        db.session.commit()
        return {}, 204


class DatasetTagBindingApi(DatasetApiResource):
    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "tag_ids",
            type=list,
            nullable=False,
            required=True,
            location="json",
            help="Tag IDs are required.",
        )
        parser.add_argument(
            "target_id",
            type=str,
            nullable=False,
            required=True,
            location="json",
            help="Target ID is required.",
        )
        args = parser.parse_args()

        if not args["tag_ids"]:
            raise ValueError("Tag IDs are required.")

        _ensure_dataset(args["target_id"], tenant_id)
        _validate_knowledge_tag_ids(args["tag_ids"], tenant_id)
        TagService.save_tag_binding(
            {
                "tag_ids": args["tag_ids"],
                "target_id": args["target_id"],
                "type": KNOWLEDGE_TAG_TYPE,
            }
        )
        return {}, 204


class DatasetTagUnbindingApi(DatasetApiResource):
    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "target_id",
            type=str,
            nullable=False,
            required=True,
            location="json",
            help="Target ID is required.",
        )
        parser.add_argument("tag_ids", type=list, nullable=True, required=False, location="json")
        parser.add_argument("tag_id", type=str, nullable=True, required=False, location="json")
        args = parser.parse_args()

        tag_ids = args.get("tag_ids") or []
        if not tag_ids and args.get("tag_id"):
            tag_ids = [args["tag_id"]]
        if not tag_ids:
            raise ValueError("Tag IDs are required.")

        _ensure_dataset(args["target_id"], tenant_id)
        _validate_knowledge_tag_ids(tag_ids, tenant_id)
        db.session.query(TagBinding).filter(
            TagBinding.target_id == args["target_id"],
            TagBinding.tag_id.in_(tag_ids),
            TagBinding.tenant_id == tenant_id,
        ).delete(synchronize_session=False)
        db.session.commit()
        return {}, 204


class DatasetBoundTagApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id):
        dataset_id = str(dataset_id)
        _ensure_dataset(dataset_id, tenant_id)

        tags = TagService.get_tags_by_target_id(KNOWLEDGE_TAG_TYPE, tenant_id, dataset_id)
        return {"data": [{"id": tag.id, "name": tag.name} for tag in tags], "total": len(tags)}, 200


api.add_resource(DatasetTagApi, "/datasets/tags")
api.add_resource(DatasetTagBindingApi, "/datasets/tags/binding")
api.add_resource(DatasetTagUnbindingApi, "/datasets/tags/unbinding")
api.add_resource(DatasetBoundTagApi, "/datasets/<uuid:dataset_id>/tags")
