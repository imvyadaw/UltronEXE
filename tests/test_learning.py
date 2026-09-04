from learning.knowledge_ingestion import KnowledgeIngestion


def test_dedupe():
    k = KnowledgeIngestion()
    assert k.ingest("a", "x")["accepted"]
    assert k.ingest("a", "x")["duplicate"]
