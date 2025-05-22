from enum import Enum


class ExternalResponseEnum(str, Enum):
    OUTPUTS = "outputs"
    RESULT = "result"
    DOCUMENTS = "documents"
