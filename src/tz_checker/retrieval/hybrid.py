import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    section_id: str | None
    location: str
    text: str
    score: float
    metadata: dict[str, Any]


# Косинусная близость отвечает за семантическую часть гибридного поиска.
def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    denominator = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0.0


# Легковесная keyword-оценка повышает точность для обозначений, ГОСТ и числовых терминов.
def keyword_score(query: str, text: str) -> float:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = re.findall(r"\w+", text.lower())
    if not query_terms or not text_terms:
        return 0.0
    return sum(1 + math.log(1 + text_terms.count(term)) for term in query_terms if term in text_terms) / len(query_terms)


def hybrid_search(query: str, query_vector: list[float], chunks: list[dict[str, Any]], limit: int = 5) -> list[SearchResult]:
    scored = []
    for chunk in chunks:
        # Семантический сигнал имеет больший вес, но точные совпадения также влияют на порядок.
        score = 0.45 * keyword_score(query, chunk["text"]) + 0.55 * max(0, cosine(query_vector, chunk.get("embedding") or []))
        scored.append(SearchResult(
            chunk_id=str(chunk["id"]), document_id=str(chunk["document_id"]),
            section_id=chunk.get("section_id"), location=chunk["location"], text=chunk["text"],
            score=score, metadata=chunk.get("metadata", {}),
        ))
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]
