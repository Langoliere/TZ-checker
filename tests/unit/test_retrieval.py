from tz_checker.retrieval.hybrid import hybrid_search


def test_hybrid_search_returns_relevant_chunk():
    chunks = [{"id": "1", "document_id": "a", "section_id": "4.2", "location": "p1", "text": "требования к надежности наработка на отказ", "embedding": [1.0, 0.0]}, {"id": "2", "document_id": "b", "section_id": "2", "location": "p2", "text": "требования к упаковке", "embedding": [0.0, 1.0]}]
    results = hybrid_search("надежность наработка", [1.0, 0.0], chunks)
    assert results[0].chunk_id == "1"
