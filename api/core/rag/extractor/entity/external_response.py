from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DocumentResult:
    page_content: str
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentResult":
        return cls(
            page_content=data.get("page_content", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ResponseData:
    data: dict[str, Any]
    error: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResponseData":
        return cls(data=data.get("data", {}), error=data.get("error"))
