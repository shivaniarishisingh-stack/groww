from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass

from src.config import settings
from src.ingest.load import Document, load_documents
from src.ingest.scrape import slug_from_url

logger = logging.getLogger(__name__)

MIN_CHUNK_CHARS = 40

# (section_slug, display_label, regex)
SECTION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("expense_ratio", "Expense ratio", r"expense\s*ratio|\bTER\b"),
    ("exit_load", "Exit load", r"exit\s*load"),
    ("min_sip", "Minimum SIP", r"min(?:imum|\.)?\s*SIP|SIP\s*(?:amount|minimum)"),
    ("lock_in", "Lock-in", r"lock[\s-]*in"),
    ("riskometer", "Riskometer", r"risk[\s-]*o[\s-]*meter|\briskometer\b"),
    ("benchmark", "Benchmark", r"\bbenchmark\b"),
    ("aum", "AUM", r"\bAUM\b|assets under management"),
    ("statements", "Statements", r"capital[\s-]*gains?|download\s+statement"),
)

COMPILED_SECTIONS = tuple(
    (slug, label, re.compile(pattern, re.IGNORECASE))
    for slug, label, pattern in SECTION_PATTERNS
)
HAS_DIGIT = re.compile(r"\d")
KNOWN_LABEL = re.compile(
    r"expense\s*ratio|\bTER\b|exit\s*load|SIP|lock[\s-]*in|riskometer|benchmark|\bAUM\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    url: str
    title: str
    section: str
    text: str
    fetched_at: str


def _documents_from_cleaned() -> list[Document] | None:
    cleaned_dir = settings.paths.cleaned
    docs: list[Document] = []
    for url in settings.urls:
        slug = slug_from_url(url)
        path = cleaned_dir / f"{slug}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        docs.append(
            Document(
                slug=slug,
                url=payload["url"],
                title=payload.get("title", ""),
                fetched_at=payload.get("fetched_at", ""),
                text=payload.get("text", ""),
            )
        )
    return docs


def documents_for_chunking() -> list[Document]:
    cleaned = _documents_from_cleaned()
    if cleaned is not None:
        return cleaned
    logger.info("Cleaned JSON missing; loading from scraped HTML")
    return load_documents(persist=False)


def _window(text: str, size: int, overlap: int, prefix: str = "") -> list[str]:
    if len(text) <= size:
        return [text]
    step_overlap = min(overlap, max(0, size - 1))
    windows: list[str] = []
    start = 0
    first = True
    while start < len(text):
        end = min(len(text), start + size)
        piece = text[start:end]
        if first:
            windows.append(piece)
            first = False
        else:
            labeled = f"{prefix}: {piece}" if prefix else piece
            windows.append(labeled)
        if end >= len(text):
            break
        start = max(start + 1, end - step_overlap)
    return windows


def _keep_chunk(text: str) -> bool:
    if len(text) >= MIN_CHUNK_CHARS:
        return True
    return bool(HAS_DIGIT.search(text) and KNOWN_LABEL.search(text))


def _label_hits(text: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for section, label, pattern in COMPILED_SECTIONS:
        for match in pattern.finditer(text):
            hits.append((match.start(), section, label))
    hits.sort(key=lambda item: item[0])
    deduped: list[tuple[int, str, str]] = []
    seen_at: set[int] = set()
    for start, section, label in hits:
        if start in seen_at:
            continue
        seen_at.add(start)
        deduped.append((start, section, label))
    return deduped


def split_structure(text: str) -> list[tuple[str, str, str]]:
    """Return (section, display_label, segment_text)."""
    if not text.strip():
        return []
    hits = _label_hits(text)
    if not hits:
        return [("overview", "Overview", text.strip())]

    segments: list[tuple[str, str, str]] = []
    first_start = hits[0][0]
    lead = text[:first_start].strip()
    if lead:
        segments.append(("overview", "Overview", lead))
    for index, (start, section, label) in enumerate(hits):
        end = hits[index + 1][0] if index + 1 < len(hits) else len(text)
        segment = text[start:end].strip()
        if segment:
            segments.append((section, label, segment))
    return segments


def split_fixed(text: str, size: int, overlap: int) -> list[tuple[str, str, str]]:
    return [
        ("window", "Window", piece)
        for piece in _window(text, size, overlap)
        if piece.strip()
    ]


def chunk_document(doc: Document) -> list[Chunk]:
    size = settings.chunking.size
    overlap = settings.chunking.overlap
    strategy = settings.chunking.strategy
    if strategy == "fixed":
        segments = split_fixed(doc.text, size, overlap)
    else:
        segments = split_structure(doc.text)

    raw_parts: list[tuple[str, str]] = []
    for section, label, segment in segments:
        for piece in _window(segment, size, overlap, prefix=label):
            if _keep_chunk(piece):
                raw_parts.append((section, piece))

    chunks: list[Chunk] = []
    width = max(3, len(str(len(raw_parts))))
    for index, (section, text) in enumerate(raw_parts, start=1):
        chunks.append(
            Chunk(
                chunk_id=f"{doc.slug}-{index:0{width}d}",
                url=doc.url,
                title=doc.title,
                section=section,
                text=text,
                fetched_at=doc.fetched_at,
            )
        )
    return chunks


def chunk_documents(documents: list[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in documents:
        chunks.extend(chunk_document(doc))
    return chunks


def persist_chunks(chunks: list[Chunk]) -> None:
    out_dir = settings.paths.chunks
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "chunks.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "chunk_id": chunk.chunk_id,
                        "url": chunk.url,
                        "title": chunk.title,
                        "section": chunk.section,
                        "text": chunk.text,
                        "fetched_at": chunk.fetched_at,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    lengths = [len(chunk.text) for chunk in chunks]
    per_url = Counter(chunk.url for chunk in chunks)
    per_section = Counter(chunk.section for chunk in chunks)
    stats = {
        "total_chunks": len(chunks),
        "per_url": dict(per_url),
        "per_section": dict(per_section),
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "avg_length": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "strategy": settings.chunking.strategy,
        "size": settings.chunking.size,
        "overlap": settings.chunking.overlap,
    }
    (out_dir / "_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote %s chunks to %s", len(chunks), jsonl_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    documents = documents_for_chunking()
    if len(documents) != len(settings.urls):
        raise ValueError(
            f"Expected {len(settings.urls)} documents, got {len(documents)}"
        )
    chunks = chunk_documents(documents)
    persist_chunks(chunks)
    print(f"Wrote {len(chunks)} chunks to {settings.paths.chunks / 'chunks.jsonl'}")
    print(f"Stats: {settings.paths.chunks / '_stats.json'}")


if __name__ == "__main__":
    main()
