from typing import Optional

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings


class KingbaseConfig(BaseSettings):
    """
    Configuration settings for KingbaseES with the KES_Vector extension
    """

    KINGBASE_HOST: Optional[str] = Field(
        description="Hostname or IP address of the KingbaseES server with the KES_Vector extension (e.g., 'localhost')",
        default=None,
    )

    KINGBASE_PORT: PositiveInt = Field(
        description="Port number on which the KingbaseES server is listening (default is 54321)",
        default=54321,
    )

    KINGBASE_USER: Optional[str] = Field(
        description="Username for authenticating with the KingbaseES database",
        default=None,
    )

    KINGBASE_PASSWORD: Optional[str] = Field(
        description="Password for authenticating with the KingbaseES database",
        default=None,
    )

    KINGBASE_DATABASE: Optional[str] = Field(
        description="Name of the KingbaseES database to connect to",
        default=None,
    )

    KINGBASE_MIN_CONNECTION: PositiveInt = Field(
        description="Min connection of the KingbaseES database",
        default=1,
    )

    KINGBASE_MAX_CONNECTION: PositiveInt = Field(
        description="Max connection of the KingbaseES database",
        default=5,
    )

    KINGBASE_FTS_CONFIG: Optional[str] = Field(
        description="Text search configuration used for full text search. "
        "Use `simple` for languages without a dictionary, `jiebacfg` (requires the `sys_jieba` extension) "
        "for Chinese. Leave empty to disable full text search.",
        default="simple",
    )

    KINGBASE_ENABLE_SEQSCAN_OFF: bool = Field(
        description="Whether to disable sequential scans in search queries, KES_Vector needs it to use the "
        "vector index on some deployments",
        default=False,
    )
