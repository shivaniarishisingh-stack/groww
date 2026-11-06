from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEMO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = DEMO_ROOT / "config.yaml"


@dataclass(frozen=True)
class ChunkingSettings:
    strategy: str
    size: int
    overlap: int


@dataclass(frozen=True)
class ChromaSettings:
    persist_dir: Path
    collection: str


@dataclass(frozen=True)
class RetrievalSettings:
    top_k: int
    min_score: float


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    model: str
    api_key: str | None


@dataclass(frozen=True)
class PathSettings:
    raw: Path
    cleaned: Path
    chunks: Path
    embeddings: Path
    traces: Path


@dataclass(frozen=True)
class UiSettings:
    welcome: str
    disclaimer: str
    examples: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    urls: tuple[str, ...]
    chunking: ChunkingSettings
    embedding_model: str
    chroma: ChromaSettings
    retrieval: RetrievalSettings
    llm: LlmSettings
    paths: PathSettings
    ui: UiSettings
    educational_link: str
    root: Path


def _as_dir(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not path.is_absolute():
        path = root / path
    return path


def _secret_value(name: str) -> str | None:
    """Return a value from Streamlit secrets, or None when unavailable.

    Streamlit raises when it runs outside a Streamlit runtime or when no
    secrets file is configured, so every access is guarded. Values are never
    logged; only the resolved string is returned to the caller.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - missing runtime/secrets must be non-fatal
        return None

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_value(name: str) -> str | None:
    """Resolve a setting from the environment/`.env` first, then secrets."""
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    return _secret_value(name)


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or CONFIG_PATH
    load_dotenv(DEMO_ROOT / ".env")

    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    root = path.parent
    paths = raw["paths"]
    return Settings(
        urls=tuple(raw["sources"]["urls"]),
        chunking=ChunkingSettings(
            strategy=raw["chunking"]["strategy"],
            size=int(raw["chunking"]["size"]),
            overlap=int(raw["chunking"]["overlap"]),
        ),
        embedding_model=raw["embedding"]["model"],
        chroma=ChromaSettings(
            persist_dir=_as_dir(root, raw["chroma"]["persist_dir"]),
            collection=raw["chroma"]["collection"],
        ),
        retrieval=RetrievalSettings(
            top_k=int(raw["retrieval"]["top_k"]),
            min_score=float(raw["retrieval"]["min_score"]),
        ),
        llm=LlmSettings(
            provider=raw["llm"]["provider"],
            model=_resolve_value("LLM_MODEL") or "",
            api_key=_resolve_value("GROQ_API_KEY"),
        ),
        paths=PathSettings(
            raw=_as_dir(root, paths["raw"]),
            cleaned=_as_dir(root, paths["cleaned"]),
            chunks=_as_dir(root, paths["chunks"]),
            embeddings=_as_dir(root, paths["embeddings"]),
            traces=_as_dir(root, paths["traces"]),
        ),
        ui=UiSettings(
            welcome=raw["ui"]["welcome"],
            disclaimer=raw["ui"]["disclaimer"],
            examples=tuple(raw["ui"]["examples"]),
        ),
        educational_link=raw["policy"]["educational_link"],
        root=root,
    )


settings = load_settings()
