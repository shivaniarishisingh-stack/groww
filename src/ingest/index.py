from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import chromadb
import numpy as np

from src.config import settings
from src.ingest.chunk import Chunk
from src.ingest.embed import (
    embed_texts,
    load_chunks,
    verify_saved_embeddings,
)

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100
MANIFEST_FILENAME = "index_manifest.json"
DISTANCE_SPACE = "cosine"
SMOKE_TOP_K = 5

_SMOKE_PATTERN = re.compile(r"Expense ratio\s+[\d.]+%", re.IGNORECASE)


def _client() -> chromadb.ClientAPI:
    persist_dir = settings.chroma.persist_dir
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def _load_phase5_artifacts() -> tuple[list[Chunk], np.ndarray, dict]:
    chunks = load_chunks()
    verify_saved_embeddings(chunks)

    vectors_path = settings.paths.embeddings / "vectors.npy"
    manifest_path = settings.paths.embeddings / "manifest.json"
    vectors = np.load(vectors_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if vectors.shape[0] != len(chunks):
        raise ValueError(
            f"Embedding rows {vectors.shape[0]} != chunk count {len(chunks)}"
        )
    if vectors.shape[1] != int(manifest["dim"]):
        raise ValueError(
            f"Embedding dimension {vectors.shape[1]} != manifest dim {manifest['dim']}"
        )
    return chunks, vectors, manifest


def _reset_collection(client: chromadb.ClientAPI):
    """Delete the old collection so a re-ingest cannot leave stale chunks."""
    name = settings.chroma.collection
    existing = {item.name for item in client.list_collections()}
    if name in existing:
        client.delete_collection(name)
        logger.info("Deleted existing Chroma collection %s", name)

    collection = client.create_collection(
        name=name,
        configuration={"hnsw": {"space": DISTANCE_SPACE}},
        metadata={
            "embedding_model": settings.embedding_model,
            "distance": DISTANCE_SPACE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    logger.info("Created Chroma collection %s (%s)", name, DISTANCE_SPACE)
    return collection


def _metadata(chunk: Chunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "url": chunk.url,
        "title": chunk.title,
        "section": chunk.section,
        "fetched_at": chunk.fetched_at,
    }


def _upsert_all(collection, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
    total = len(chunks)
    for start in range(0, total, UPSERT_BATCH_SIZE):
        stop = min(start + UPSERT_BATCH_SIZE, total)
        batch = chunks[start:stop]
        collection.upsert(
            ids=[chunk.chunk_id for chunk in batch],
            embeddings=np.ascontiguousarray(vectors[start:stop]),
            documents=[chunk.text for chunk in batch],
            metadatas=[_metadata(chunk) for chunk in batch],
        )
        logger.info("Upserted chunks %s-%s of %s", start + 1, stop, total)


def verify_index(
    collection, chunks: Sequence[Chunk], vectors: np.ndarray
) -> dict:
    """Read every expected record back and compare it to Phase 4/5 artifacts."""
    expected_ids = [chunk.chunk_id for chunk in chunks]
    unknown_urls = {chunk.url for chunk in chunks} - set(settings.urls)
    if unknown_urls:
        raise ValueError(
            "Chunks contain URLs outside the allowlist: " + ", ".join(sorted(unknown_urls))
        )

    count = collection.count()
    if count != len(chunks):
        raise ValueError(
            f"Chroma count {count} != expected {len(chunks)} chunks"
        )

    stored = collection.get(
        ids=expected_ids,
        include=["documents", "metadatas", "embeddings"],
    )
    stored_ids = stored.get("ids") or []
    missing = sorted(set(expected_ids) - set(stored_ids))
    extra = sorted(set(stored_ids) - set(expected_ids))
    if missing:
        raise ValueError(f"Missing chunk IDs in Chroma: {', '.join(missing)}")
    if extra:
        raise ValueError(f"Unexpected chunk IDs in Chroma: {', '.join(extra)}")
    if len(stored_ids) != len(chunks):
        raise ValueError(
            f"Chroma returned {len(stored_ids)} records, expected {len(chunks)}"
        )

    position = {chunk_id: index for index, chunk_id in enumerate(stored_ids)}
    stored_embeddings = np.asarray(stored["embeddings"], dtype=np.float32)
    for index, chunk in enumerate(chunks):
        stored_index = position[chunk.chunk_id]
        if stored["documents"][stored_index] != chunk.text:
            raise ValueError(f"Document mismatch for {chunk.chunk_id}")
        if stored["metadatas"][stored_index] != _metadata(chunk):
            raise ValueError(f"Metadata mismatch for {chunk.chunk_id}")
        if not np.allclose(
            stored_embeddings[stored_index], vectors[index], atol=1e-6
        ):
            raise ValueError(f"Embedding mismatch for {chunk.chunk_id}")

    urls = sorted({chunk.url for chunk in chunks})
    if urls != sorted(settings.urls):
        raise ValueError(
            "Stored source URLs do not match the five allowlisted URLs"
        )

    return {
        "count": count,
        "unique_ids": len(set(expected_ids)),
        "source_urls": urls,
        "documents_match": True,
        "metadata_match": True,
        "embeddings_match": True,
    }


def _smoke_query_text(chunks: Sequence[Chunk]) -> str:
    for chunk in chunks:
        if chunk.section == "expense_ratio" and _SMOKE_PATTERN.search(chunk.text):
            return chunk.text
    return chunks[0].text


def smoke_query(collection, chunks: Sequence[Chunk]) -> dict:
    """Query Chroma with a stored chunk and require that chunk at rank 1."""
    query_text = _smoke_query_text(chunks)
    expected_id = next(
        chunk.chunk_id for chunk in chunks if chunk.text == query_text
    )
    result = collection.query(
        query_embeddings=embed_texts([query_text]),
        n_results=min(SMOKE_TOP_K, len(chunks)),
        include=["documents", "metadatas", "distances"],
    )
    ids = result["ids"][0]
    distances = result["distances"][0]
    if not ids or ids[0] != expected_id:
        raise ValueError(
            f"Smoke query for {expected_id} returned {ids} at rank 1"
        )

    return {
        "query_chunk_id": expected_id,
        "query_preview": query_text[:160],
        "rank": 1,
        "top_chunk_ids": ids,
        "top_distances": [round(float(value), 6) for value in distances],
        "passed": True,
    }


def persist_index_manifest(
    collection,
    chunks: Sequence[Chunk],
    embedding_manifest: dict,
    smoke: dict,
    *,
    elapsed_seconds: float,
) -> Path:
    out_dir = settings.chroma.persist_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "collection": settings.chroma.collection,
        "persist_dir": settings.chroma.persist_dir.relative_to(settings.root).as_posix(),
        "count": collection.count(),
        "dim": int(embedding_manifest["dim"]),
        "embedding_model": settings.embedding_model,
        "distance": DISTANCE_SPACE,
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "source_urls": sorted({chunk.url for chunk in chunks}),
        "embedding_manifest_created_at": embedding_manifest.get("created_at"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "smoke_query": smoke,
    }
    path = out_dir / MANIFEST_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_index() -> dict:
    chunks, vectors, embedding_manifest = _load_phase5_artifacts()
    started = time.perf_counter()

    client = _client()
    collection = _reset_collection(client)
    _upsert_all(collection, chunks, vectors)

    verification = verify_index(collection, chunks, vectors)
    smoke = smoke_query(collection, chunks)
    elapsed = time.perf_counter() - started
    manifest_path = persist_index_manifest(
        collection,
        chunks,
        embedding_manifest,
        smoke,
        elapsed_seconds=elapsed,
    )

    return {
        **verification,
        "collection": settings.chroma.collection,
        "dim": int(vectors.shape[1]),
        "smoke": smoke,
        "manifest": str(manifest_path),
        "elapsed_seconds": round(elapsed, 2),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = run_index()
    print(
        f"Stored {summary['count']} chunks in Chroma collection "
        f"{summary['collection']!r}"
    )
    print(f"Dimension: {summary['dim']} | distance: {DISTANCE_SPACE}")
    print(f"Source URLs: {len(summary['source_urls'])}")
    print(
        "Smoke query: "
        f"{summary['smoke']['query_chunk_id']} -> "
        f"rank {summary['smoke']['rank']} "
        f"(distance {summary['smoke']['top_distances'][0]})"
    )
    print(f"Manifest: {summary['manifest']}")


if __name__ == "__main__":
    main()
