"""Run the full ingest pipeline: scrape -> load -> chunk -> embed -> index."""

import logging

from src.ingest.chunk import main as chunk_main
from src.ingest.embed import main as embed_main
from src.ingest.index import main as index_main
from src.ingest.load import main as load_main
from src.ingest.scrape import main as scrape_main

logger = logging.getLogger(__name__)

STAGES = (
    ("scrape", scrape_main),
    ("load", load_main),
    ("chunk", chunk_main),
    ("embed", embed_main),
    ("index", index_main),
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for name, stage in STAGES:
        logger.info("=== Ingest stage: %s ===", name)
        stage()
    logger.info("=== Ingest complete ===")


if __name__ == "__main__":
    main()
