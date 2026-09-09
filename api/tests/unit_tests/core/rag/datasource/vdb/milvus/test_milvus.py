import pytest
from pydantic.error_wrappers import ValidationError

from core.rag.datasource.vdb.milvus.milvus_vector import MilvusConfig


def test_default_value():
    valid_config = {"uri": "http://localhost:19530", "user": "root", "password": "Milvus"}

    for key in valid_config:
        config = valid_config.copy()
        del config[key]
        with pytest.raises(ValidationError) as e:
            MilvusConfig(**config)
        assert e.value.errors()[0]["msg"] == f"Value error, config MILVUS_{key.upper()} is required"

    config = MilvusConfig(**valid_config)
    assert config.database == "default"


def test_analyzer_params():
    config = MilvusConfig(
        uri="http://localhost:19530",
        user="root",
        password="Milvus",
        analyzer_params='{"type":"chinese"}',
    )

    assert config.analyzer_params == {"type": "chinese"}

    with pytest.raises(ValidationError) as e:
        MilvusConfig(
            uri="http://localhost:19530",
            user="root",
            password="Milvus",
            analyzer_params="{invalid",
        )

    assert e.value.errors()[0]["msg"] == "Value error, config MILVUS_ANALYZER_PARAMS must be a valid JSON object"
