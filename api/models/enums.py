from enum import StrEnum


class CreatedByRole(StrEnum):
    ACCOUNT = "account"
    END_USER = "end_user"


class UserFrom(StrEnum):
    ACCOUNT = "account"
    END_USER = "end-user"


class WorkflowRunTriggeredFrom(StrEnum):
    DEBUGGING = "debugging"
    APP_RUN = "app-run"


class DocMetadataField(StrEnum):
    doc_source = "doc_source"
    page_id = "page_id"
    doc_hash = "doc_hash"
    auto_upgrade = "auto_upgrade"
