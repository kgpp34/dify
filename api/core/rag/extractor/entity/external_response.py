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
class OutputResult:
    result: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputResult":
        return cls(
            result=data.get("result", {})
        )


@dataclass
class ResponseData:
    task_id: str
    workflow_run_id: str
    data: Dict[str, Any]
    error: Optional[str]
    elapsed_time: float
    total_tokens: int
    total_steps: int
    created_at: int
    finished_at: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseData":
        return cls(
            task_id=data.get("task_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            data=data.get("data", {}),
            error=data.get("error"),
            elapsed_time=data.get("elapsed_time", 0.0),
            total_tokens=data.get("total_tokens", 0),
            total_steps=data.get("total_steps", 0),
            created_at=data.get("created_at", 0),
            finished_at=data.get("finished_at", 0),
        )
