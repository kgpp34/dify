from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class DocumentResult:
    page_content: str
    metadata: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentResult":
        return cls(
            page_content=data.get("page_content", "test"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ResponseData:
    data: Dict[str, Any]
    error: Optional[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseData":
        return cls(
            data=data.get("data", {}),
            error=data.get("error")
        )
