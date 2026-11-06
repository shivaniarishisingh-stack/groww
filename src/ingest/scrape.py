from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
EMPTY_PAGE_CHARS = 500


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-").lower()
    if not slug:
        raise ValueError(f"Could not derive slug from URL: {url}")
    return slug


def assert_allowlisted(url: str) -> None:
    if url not in settings.urls:
        raise ValueError(
            f"URL is not in the allowlist of {len(settings.urls)} pages: {url}"
        )


def _is_probably_empty(html: str) -> bool:
    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", stripped)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) < EMPTY_PAGE_CHARS


def fetch_one(client: httpx.Client, url: str) -> tuple[str, int]:
    assert_allowlisted(url)
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=True)
            if response.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"Server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
                logger.warning(
                    "Retry %s/%s for %s (status %s)",
                    attempt,
                    MAX_RETRIES,
                    url,
                    response.status_code,
                )
                continue
            if response.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"Client error {response.status_code} for {url}",
                    request=response.request,
                    response=response,
                )
            return response.text, response.status_code
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            logger.warning(
                "Retry %s/%s for %s (%s)", attempt, MAX_RETRIES, url, exc
            )
    raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts") from last_error


def save_raw(url: str, html: str, status_code: int, raw_dir: Path) -> Path:
    slug = slug_from_url(url)
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_path = raw_dir / f"{slug}.html"
    meta_path = raw_dir / f"{slug}.meta.json"
    html_path.write_text(html, encoding="utf-8")
    meta = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "http_status": status_code,
        "slug": slug,
        "bytes": len(html.encode("utf-8")),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if _is_probably_empty(html):
        logger.warning(
            "Cleaned-looking text is very short for %s; page may be a JS shell",
            url,
        )
    return html_path


def scrape_allowlisted_pages() -> list[Path]:
    """Fetch only config sources.urls. Never crawls hrefs on those pages."""
    written: list[Path] = []
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS) as client:
        for url in settings.urls:
            assert_allowlisted(url)
            html, status = fetch_one(client, url)
            path = save_raw(url, html, status, settings.paths.raw)
            logger.info("Saved %s (%s)", path, status)
            written.append(path)
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    paths = scrape_allowlisted_pages()
    print(f"Scraped {len(paths)} allowlisted pages into {settings.paths.raw}")
    for path in paths:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
