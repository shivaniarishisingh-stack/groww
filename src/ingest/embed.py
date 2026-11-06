from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from src.config import settings
from src.ingest.chunk import Chunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 32
VECTORS_FILENAME = "vectors.npy"
MANIFEST_FILENAME = "manifest.json"
_WHITESPACE = re.compile(r"\s+")

_model = None


def normalize_text(text: str) -> str:
    """Collapse whitespace before embedding (model still handles casing)."""
    return _WHITESPACE.sub(" ", text).strip()


def load_chunks(path: Path | None = None) -> list[Chunk]:
    """Read the Phase 4 chunk artifact and validate it before embedding."""
    chunks_path = path or (settings.paths.chunks / "chunks.jsonl")
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"No chunks found at {chunks_path}. Run: python -m src.ingest.chunk"
        )

    chunks: list[Chunk] = []
    with chunks_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                chunk = Chunk(
                    chunk_id=payload["chunk_id"],
                    url=payload["url"],
                    title=payload.get("title", ""),
                    section=payload.get("section", ""),
                    text=payload["text"],
                    fetched_at=payload.get("fetched_at", ""),
                )
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Invalid chunk at {chunks_path}:{line_number}: {exc}"
                ) from exc
            if not chunk.text.strip():
                raise ValueError(f"Empty chunk text at {chunks_path}:{line_number}")
            chunks.append(chunk)

    if not chunks:
        raise ValueError(f"No chunks found in {chunks_path}")

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    duplicates = sorted({cid for cid in chunk_ids if chunk_ids.count(cid) > 1})
    if duplicates:
        raise ValueError(f"Duplicate chunk_id values: {', '.join(duplicates)}")

    stats_path = settings.paths.chunks / "_stats.json"
    if stats_path.exists():
        expected = json.loads(stats_path.read_text(encoding="utf-8")).get("total_chunks")
        if expected is not None and int(expected) != len(chunks):
            raise ValueError(
                f"Chunk count mismatch: _stats.json says {expected}, "
                f"chunks.jsonl has {len(chunks)}"
            )

    return chunks


def get_model():
    """Load the configured SentenceTransformer once per process."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """Embed texts with the same model used at ingest and query time.

    Returns a float32 matrix with one L2-normalized vector per input text,
    so cosine similarity is a dot product in Chroma.
    """
    if not texts:
        raise ValueError("embed_texts() requires at least one text")

    cleaned = [normalize_text(text) for text in texts]
    if any(not text for text in cleaned):
        raise ValueError("Cannot embed empty text")

    model = get_model()
    vectors = model.encode(
        cleaned,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_chunks(chunks: Sequence[Chunk]) -> np.ndarray:
    return embed_texts([chunk.text for chunk in chunks])


def _verify_vectors(
    vectors: np.ndarray, chunks: Sequence[Chunk], dimension: int
) -> None:
    expected_shape = (len(chunks), dimension)
    if vectors.shape != expected_shape:
        raise ValueError(
            f"Embedding shape mismatch: expected {expected_shape}, got {vectors.shape}"
        )
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding matrix contains NaN or infinite values")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        raise ValueError("Embeddings are not L2-normalized")


def persist_embeddings(
    chunks: Sequence[Chunk],
    vectors: np.ndarray,
    *,
    elapsed_seconds: float,
) -> Path:
    out_dir = settings.paths.embeddings
    out_dir.mkdir(parents=True, exist_ok=True)

    vectors_path = out_dir / VECTORS_FILENAME
    np.save(vectors_path, vectors)

    manifest = {
        "model": settings.embedding_model,
        "dim": int(vectors.shape[1]),
        "count": int(vectors.shape[0]),
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "normalized": True,
        "dtype": str(vectors.dtype),
        "batch_size": BATCH_SIZE,
        "vectors_file": VECTORS_FILENAME,
        "chunks_file": (settings.paths.chunks / "chunks.jsonl")
        .relative_to(settings.root)
        .as_posix(),
        "embedding_seconds": round(elapsed_seconds, 2),
    }
    manifest_path = out_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


def verify_saved_embeddings(chunks: Sequence[Chunk]) -> dict:
    """Reload artifacts from disk and assert Phase 5's contract."""
    out_dir = settings.paths.embeddings
    manifest_path = out_dir / MANIFEST_FILENAME
    vectors_path = out_dir / VECTORS_FILENAME
    if not manifest_path.exists() or not vectors_path.exists():
        raise FileNotFoundError("Run: python -m src.ingest.embed")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vectors = np.load(vectors_path)
    dimension = int(manifest["dim"])

    if manifest["model"] != settings.embedding_model:
        raise ValueError(
            "Embedding model changed since Phase 5 ran: manifest has "
            f"{manifest['model']!r}, config has {settings.embedding_model!r}. "
            "Re-run: python -m src.ingest.embed"
        )
    if not manifest.get("normalized"):
        raise ValueError("Manifest does not record normalized embeddings")
    if manifest["count"] != len(chunks):
        raise ValueError(
            f"Manifest count {manifest['count']} != chunk count {len(chunks)}"
        )
    if manifest["chunk_ids"] != [chunk.chunk_id for chunk in chunks]:
        raise ValueError("Manifest chunk_ids do not match chunks.jsonl order")
    _verify_vectors(vectors, chunks, dimension)

    return {
        "model": manifest["model"],
        "dim": dimension,
        "count": int(vectors.shape[0]),
        "shape": list(vectors.shape),
        "dtype": str(vectors.dtype),
        "norm_min": float(np.linalg.norm(vectors, axis=1).min()),
        "norm_max": float(np.linalg.norm(vectors, axis=1).max()),
    }


def run_embedding() -> dict:
    chunks = load_chunks()
    logger.info("Embedding %s chunks with %s", len(chunks), settings.embedding_model)
    started = time.perf_counter()
    vectors = embed_chunks(chunks)
    elapsed = time.perf_counter() - started

    _verify_vectors(vectors, chunks, int(vectors.shape[1]))
    manifest_path = persist_embeddings(chunks, vectors, elapsed_seconds=elapsed)
    summary = verify_saved_embeddings(chunks)
    summary["manifest"] = str(manifest_path)
    summary["vectors"] = str(settings.paths.embeddings / VECTORS_FILENAME)
    summary["embedding_seconds"] = round(elapsed, 2)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = run_embedding()
    print(f"Embedded {summary['count']} chunks with {summary['model']}")
    print(f"Dimension: {summary['dim']}")
    print(f"Vectors: {summary['shape']} ({summary['dtype']})")
    print(f"L2 norms: {summary['norm_min']:.6f} to {summary['norm_max']:.6f}")
    print(f"Manifest: {summary['manifest']}")
    print(f"Vectors: {summary['vectors']}")


if __name__ == "__main__":
    main()
