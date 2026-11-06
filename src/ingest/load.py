from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from src.config import settings
from src.ingest.scrape import slug_from_url

logger = logging.getLogger(__name__)

DROP_TAGS = ("script", "style", "nav", "footer", "noscript", "svg", "iframe")


@dataclass(frozen=True)
class Document:
    slug: str
    url: str
    title: str
    fetched_at: str
    text: str


def _read_meta(html_path: Path) -> dict:
    meta_path = html_path.with_suffix("").with_name(html_path.stem + ".meta.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _title_from_soup(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return re.sub(r"\s+", " ", soup.title.string).strip()
    heading = soup.find(["h1", "h2"])
    if heading:
        return re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
    return ""


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True, id=re.compile(r"cookie|consent|banner", re.I)):
        tag.decompose()
    for tag in soup.find_all(True, class_=re.compile(r"cookie|consent|banner", re.I)):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def parse_html(html: str, *, url: str, slug: str, fetched_at: str) -> Document:
    soup = BeautifulSoup(html, "lxml")
    title = _title_from_soup(soup)
    text = _visible_text(soup)
    return Document(
        slug=slug,
        url=url,
        title=title,
        fetched_at=fetched_at,
        text=text,
    )


def _document_from_html_file(html_path: Path) -> Document | None:
    slug = html_path.stem
    meta = _read_meta(html_path)
    url = meta.get("url", "")
    if not url:
        expected = {slug_from_url(item): item for item in settings.urls}
        url = expected.get(slug, "")
    if not url:
        logger.warning("Skipping %s: no URL in sidecar and slug is not allowlisted", html_path.name)
        return None
    if url not in settings.urls:
        logger.warning("Skipping %s: URL is not allowlisted (%s)", html_path.name, url)
        return None
    html = html_path.read_text(encoding="utf-8", errors="replace")
    doc = parse_html(
        html,
        url=url,
        slug=slug,
        fetched_at=str(meta.get("fetched_at", "")),
    )
    if not doc.text:
        logger.warning("Loaded empty text for %s (possible JS shell)", url)
    return doc


def persist_cleaned(documents: list[Document]) -> Path:
    cleaned_dir = settings.paths.cleaned
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    for extra in cleaned_dir.glob("*.json"):
        extra.unlink()
    manifest = []
    for doc in documents:
        payload = {
            "url": doc.url,
            "title": doc.title,
            "fetched_at": doc.fetched_at,
            "text": doc.text,
        }
        (cleaned_dir / f"{doc.slug}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest.append(
            {
                "slug": doc.slug,
                "url": doc.url,
                "fetched_at": doc.fetched_at,
                "title": doc.title,
                "text_length": len(doc.text),
            }
        )
    path = cleaned_dir / "_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_documents(*, persist: bool = False) -> list[Document]:
    """Read scraped HTML from disk. Does not fetch URLs or follow links."""
    raw_dir = settings.paths.raw
    html_files = sorted(raw_dir.glob("*.html"))
    if not html_files:
        raise FileNotFoundError(
            f"No HTML files in {raw_dir}. Run: python -m src.ingest.scrape"
        )

    by_url: dict[str, Document] = {}
    for html_path in html_files:
        doc = _document_from_html_file(html_path)
        if doc is None:
            continue
        by_url[doc.url] = doc

    missing = [url for url in settings.urls if url not in by_url]
    if missing:
        raise FileNotFoundError(
            "Missing scraped HTML for allowlisted URL(s):\n  " + "\n  ".join(missing)
        )
    if len(by_url) != len(settings.urls):
        raise ValueError(
            f"Expected {len(settings.urls)} documents, loaded {len(by_url)}"
        )

    documents = [by_url[url] for url in settings.urls]
    if persist:
        persist_cleaned(documents)
    return documents


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    documents = load_documents(persist=True)
    print(f"Loaded {len(documents)} documents into {settings.paths.cleaned}")
    for doc in documents:
        print(f"  {doc.slug}: {len(doc.text)} chars | {doc.title[:80]}")


if __name__ == "__main__":
    main()
