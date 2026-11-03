from core.rag.datasource.vdb.kingbase.kingbase import Kingbase, KingbaseConfig
from tests.integration_tests.vdb.test_vector_store import (
    AbstractVectorTest,
    get_example_text,
    setup_mock_redis,
)


class KingbaseTest(AbstractVectorTest):
    def __init__(self):
        super().__init__()
        self.vector = Kingbase(
            collection_name=self.collection_name,
            config=KingbaseConfig(
                host="localhost",
                port=54321,
                user="system",
                password="123456",
                database="dify",
                min_connection=1,
                max_connection=5,
                fts_config="simple",
            ),
        )


def test_kingbase(setup_mock_redis):
    KingbaseTest().run_all_tests()
