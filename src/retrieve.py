from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import chromadb
import numpy as np

from src.config import settings
from src.ingest.embed import embed_texts, normalize_text
from src.policy import refusal_message, scan

logger = logging.getLogger(__name__)

SECTION_WEIGHT = 0.5
FACT_EVIDENCE_BONUS = 0.1
CANDIDATE_MULTIPLIER = 10
MIN_CANDIDATES = 50


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    url: str
    title: str
    section: str
    text: str
    fetched_at: str
    score: float
    vector_score: float
    distance: float
    fact_match: bool

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "url": self.url,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "fetched_at": self.fetched_at,
            "score": self.score,
            "vector_score": self.vector_score,
            "distance": self.distance,
            "fact_match": self.fact_match,
        }


@dataclass(frozen=True)
class RetrievalResult:
    intent: str
    hits: tuple[RetrievalHit, ...]
    pii_type: str | None = None
    scheme_urls: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()
    trace_path: Path | None = None
    trace_written: bool = False
    top_k: int = 0
    min_score: float = 0.0
    candidate_count: int = 0

    @property
    def found(self) -> bool:
        return bool(self.hits)


def _url_for_marker(marker: str) -> str | None:
    for url in settings.urls:
        if marker in url:
            return url
    return None


_SCHEME_RULES: tuple[tuple[str, re.Pattern[str], str | None], ...] = (
    ("large_cap", re.compile(r"\blarge[\s-]*cap\b", re.IGNORECASE), "large-cap"),
    ("mid_cap", re.compile(r"\bmid[\s-]*cap\b", re.IGNORECASE), "mid-cap"),
    ("elss", re.compile(r"\belss\b|\btax\s*saver\b", re.IGNORECASE), "elss"),
    (
        "flexi_cap",
        re.compile(r"\bflexi[\s-]*cap\b|\bhdfc\s+equity\s+fund\b", re.IGNORECASE),
        "equity-fund",
    ),
)
_AMC_PATTERN = re.compile(r"\bamc\b|\bhdfc\s+mutual\s+fund\b", re.IGNORECASE)

_SECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("expense_ratio", re.compile(r"expense\s*ratio|\bter\b", re.IGNORECASE)),
    ("exit_load", re.compile(r"exit\s*load", re.IGNORECASE)),
    (
        "min_sip",
        re.compile(
            r"minimum\s*sip|min(?:imum|\.)?\s*(?:for\s*)?sip|\bsip\b",
            re.IGNORECASE,
        ),
    ),
    ("lock_in", re.compile(r"lock[\s-]*in", re.IGNORECASE)),
    (
        "riskometer",
        re.compile(r"risk[\s-]*o[\s-]*meter|\briskometer\b", re.IGNORECASE),
    ),
    ("benchmark", re.compile(r"\bbenchmark\b", re.IGNORECASE)),
    ("aum", re.compile(r"\baum\b|assets\s+under\s+management", re.IGNORECASE)),
    (
        "statements",
        re.compile(
            r"capital[\s-]*gains?|download\s+(?:a\s+)?statement|\bstatement\b",
            re.IGNORECASE,
        ),
    ),
)


_FACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "expense_ratio": re.compile(
        r"expense\s*ratio\s+\d+(?:\.\d+)?\s*%", re.IGNORECASE
    ),
    "exit_load": re.compile(
        r"exit\s*load\s+(?:of\s+)?\d+(?:\.\d+)?\s*%", re.IGNORECASE
    ),
    "min_sip": re.compile(
        r"(?:minimum\s*sip|min(?:imum|\.)?\s*(?:for\s*)?sip)"
        r"[^.\n]{0,50}?(?:₹|rs\.?)\s*[\d,]+",
        re.IGNORECASE,
    ),
    "lock_in": re.compile(
        r"lock[\s-]*in[^.\n]{0,80}?(?:\d+\s*(?:years?|yrs?)|3\s*y)",
        re.IGNORECASE,
    ),
    "benchmark": re.compile(
        r"benchmark[^.\n]{0,80}?(?:index|nifty|sensex)", re.IGNORECASE
    ),
    "aum": re.compile(
        r"\baum\b[^.\n]{0,50}?(?:₹|rs\.?)\s*[\d,]+", re.IGNORECASE
    ),
    "statements": re.compile(
        r"download|statement|capital\s*gains", re.IGNORECASE
    ),
}


def _has_fact_evidence(text: str, sections: Sequence[str]) -> bool:
    return any(
        _FACT_PATTERNS[section].search(text)
        for section in sections
        if section in _FACT_PATTERNS
    )


def detect_schemes(question: str) -> tuple[str, ...]:
    """Map scheme names in the question to their allowlisted Groww URLs."""
    urls: list[str] = []
    for _label, pattern, marker in _SCHEME_RULES:
        if not pattern.search(question):
            continue
        url = _url_for_marker(marker) if marker else None
        if url and url not in urls:
            urls.append(url)

    if not urls and _AMC_PATTERN.search(question):
        amc_url = _url_for_marker("/amc/")
        if amc_url:
            urls.append(amc_url)
    return tuple(urls)


def detect_sections(question: str) -> tuple[str, ...]:
    return tuple(
        name for name, pattern in _SECTION_RULES if pattern.search(question)
    )


def _get_collection() -> Any | None:
    client = chromadb.PersistentClient(path=str(settings.chroma.persist_dir))
    names = {item.name for item in client.list_collections()}
    if settings.chroma.collection not in names:
        logger.warning(
            "Chroma collection %s is missing. Run: python -m src.ingest.index",
            settings.chroma.collection,
        )
        return None
    return client.get_collection(settings.chroma.collection)


def _where_for_urls(urls: Sequence[str]) -> dict | None:
    if not urls:
        return None
    if len(urls) == 1:
        return {"url": urls[0]}
    return {"url": {"$in": list(urls)}}


def _available_count(collection: Any, where: dict | None) -> int:
    if where is None:
        return int(collection.count())
    result = collection.get(where=where, include=[])
    return len(result.get("ids", []))


def _candidate_count(
    available: int,
    *,
    top_k: int,
    sections: Sequence[str],
) -> int:
    if available <= 0:
        return 0
    # A section-aware question considers all chunks for the selected scheme(s),
    # so the matching section cannot be cut off by vector-only ranking.
    if sections:
        return available
    return min(available, max(top_k * CANDIDATE_MULTIPLIER, MIN_CANDIDATES))


def _query(
    collection: Any,
    vector: np.ndarray,
    n_results: int,
    where: dict | None,
) -> dict:
    return collection.query(
        query_embeddings=np.asarray([vector], dtype=np.float32),
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


def _build_hits(
    result: dict,
    *,
    sections: Sequence[str],
    min_score: float,
    top_k: int,
) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for chunk_id, document, metadata, distance in zip(
        ids, documents, metadatas, distances
    ):
        vector_score = max(-1.0, min(1.0, 1.0 - float(distance)))
        if vector_score < min_score:
            continue

        section = str(metadata.get("section", ""))
        if sections and section not in sections:
            continue

        fact_match = _has_fact_evidence(str(document), sections)
        score = vector_score
        if sections:
            score = (1.0 - SECTION_WEIGHT) * vector_score + SECTION_WEIGHT
            if fact_match:
                score = min(1.0, score + FACT_EVIDENCE_BONUS)

        hits.append(
            RetrievalHit(
                chunk_id=str(chunk_id),
                url=str(metadata.get("url", "")),
                title=str(metadata.get("title", "")),
                section=section,
                text=str(document),
                fetched_at=str(metadata.get("fetched_at", "")),
                score=round(float(score), 6),
                vector_score=round(float(vector_score), 6),
                distance=round(float(distance), 6),
                fact_match=fact_match,
            )
        )

    hits.sort(key=lambda hit: (-hit.score, -hit.vector_score, hit.chunk_id))
    return hits[:top_k]


def _trace_payload(
    *,
    question: str,
    intent: str,
    hits: Sequence[RetrievalHit],
    top_k: int,
    min_score: float,
    scheme_urls: Sequence[str],
    sections: Sequence[str],
    candidate_count: int,
    pii_type: str | None,
) -> dict:
    asked_at = datetime.now(timezone.utc).isoformat()
    if pii_type:
        # No query hash, query text, or PII value is written.
        return {
            "asked_at": asked_at,
            "query_redacted": True,
            "intent": "refuse_pii",
            "pii_type": pii_type,
            "hits": [],
        }

    normalized = normalize_text(question).lower()
    query_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return {
        "asked_at": asked_at,
        "query_redacted": True,
        "query_hash": query_hash,
        "query_length": len(question),
        "intent": intent,
        "top_k": top_k,
        "min_score": min_score,
        "candidate_count": candidate_count,
        "collection": settings.chroma.collection,
        "embedding_model": settings.embedding_model,
        "scheme_urls": list(scheme_urls),
        "sections_asked": list(sections),
        "hits": [hit.as_dict() for hit in hits],
    }


def _persist_trace(payload: dict, *, pii: bool) -> Path | None:
    traces_dir = settings.paths.traces
    traces_dir.mkdir(parents=True, exist_ok=True)
    if pii:
        path = traces_dir / "refuse_pii.json"
    else:
        path = traces_dir / f"{payload['query_hash']}.json"

    try:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write retrieval trace %s: %s", path, exc)
        return None
    return path


def retrieve(
    question: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    persist_trace: bool = True,
) -> RetrievalResult:
    """Embed the question, search Chroma, rerank, and persist a safe trace."""
    text = normalize_text(question)
    if not text:
        raise ValueError("Question must not be empty")

    k = int(top_k if top_k is not None else settings.retrieval.top_k)
    threshold = float(
        min_score if min_score is not None else settings.retrieval.min_score
    )
    if k <= 0:
        raise ValueError("top_k must be greater than zero")

    decision = scan(text)
    scheme_urls = detect_schemes(text)
    sections = detect_sections(text)

    if decision.intent != "fact":
        payload = _trace_payload(
            question=question,
            intent=decision.intent,
            hits=(),
            top_k=k,
            min_score=threshold,
            scheme_urls=scheme_urls,
            sections=sections,
            candidate_count=0,
            pii_type=decision.pii_type,
        )
        trace_path = (
            _persist_trace(
                payload,
                pii=decision.intent == "refuse_pii",
            )
            if persist_trace
            else None
        )
        return RetrievalResult(
            intent=decision.intent,
            hits=(),
            pii_type=decision.pii_type,
            scheme_urls=scheme_urls,
            sections=sections,
            trace_path=trace_path,
            trace_written=trace_path is not None,
            top_k=k,
            min_score=threshold,
            candidate_count=0,
        )

    collection = _get_collection()
    if collection is None:
        payload = _trace_payload(
            question=question,
            intent="out_of_corpus",
            hits=(),
            top_k=k,
            min_score=threshold,
            scheme_urls=scheme_urls,
            sections=sections,
            candidate_count=0,
            pii_type=None,
        )
        trace_path = _persist_trace(payload, pii=False) if persist_trace else None
        return RetrievalResult(
            intent="out_of_corpus",
            hits=(),
            scheme_urls=scheme_urls,
            sections=sections,
            trace_path=trace_path,
            trace_written=trace_path is not None,
            top_k=k,
            min_score=threshold,
        )

    where = _where_for_urls(scheme_urls)
    available = _available_count(collection, where)
    candidate_count = _candidate_count(available, top_k=k, sections=sections)

    if candidate_count == 0:
        payload = _trace_payload(
            question=question,
            intent="out_of_corpus",
            hits=(),
            top_k=k,
            min_score=threshold,
            scheme_urls=scheme_urls,
            sections=sections,
            candidate_count=0,
            pii_type=None,
        )
        trace_path = _persist_trace(payload, pii=False) if persist_trace else None
        return RetrievalResult(
            intent="out_of_corpus",
            hits=(),
            scheme_urls=scheme_urls,
            sections=sections,
            trace_path=trace_path,
            trace_written=trace_path is not None,
            top_k=k,
            min_score=threshold,
            candidate_count=0,
        )

    vector = embed_texts([text])[0]
    raw = _query(collection, vector, candidate_count, where)
    hits = _build_hits(
        raw,
        sections=sections,
        min_score=threshold,
        top_k=k,
    )
    intent = "fact" if hits else "out_of_corpus"

    payload = _trace_payload(
        question=question,
        intent=intent,
        hits=hits,
        top_k=k,
        min_score=threshold,
        scheme_urls=scheme_urls,
        sections=sections,
        candidate_count=candidate_count,
        pii_type=None,
    )
    trace_path = _persist_trace(payload, pii=False) if persist_trace else None

    return RetrievalResult(
        intent=intent,
        hits=tuple(hits),
        scheme_urls=scheme_urls,
        sections=sections,
        trace_path=trace_path,
        trace_written=trace_path is not None,
        top_k=k,
        min_score=threshold,
        candidate_count=candidate_count,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Query the Groww HDFC FAQ corpus.")
    parser.add_argument("question", nargs="+", help="Question to retrieve chunks for")
    args = parser.parse_args()
    question = " ".join(args.question)

    result = retrieve(question)
    print(f"Intent: {result.intent}")
    if result.pii_type:
        print(f"PII type: {result.pii_type} (query not stored)")
    if result.intent != "fact":
        print(refusal_message(result.intent))
        print(f"Source: {settings.educational_link}")
        if result.trace_path:
            print(f"Trace: {result.trace_path}")
        return
    print(f"Schemes: {', '.join(result.scheme_urls) or 'all'}")
    print(f"Sections: {', '.join(result.sections) or 'any'}")
    for index, hit in enumerate(result.hits, start=1):
        print(
            f"{index}. score={hit.score:.4f} vector={hit.vector_score:.4f} "
            f"fact={hit.fact_match} {hit.chunk_id} [{hit.section}] {hit.url}"
        )
        print(f"   {hit.text[:220]}")
    if result.trace_path:
        print(f"Trace: {result.trace_path}")


if __name__ == "__main__":
    main()
