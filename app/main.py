"""Phase 1 smoke test for the WordPress client.

By default the test post is created as a **draft**, so nothing experimental is
published to the live site. Pass ``--publish`` to publish it — only do this
with explicit approval.
"""

from __future__ import annotations

import argparse
import logging
import sys
import zlib
from zlib import compressobj, crc32

from .config import Settings
from .wordpress import PostResponse, WordPressClient, WordPressError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("wordpress_automation")


def _make_png(width: int = 8, height: int = 8) -> bytes:
    """Tiny solid-color PNG built with stdlib zlib (no Pillow dependency).

    Shortcut: single-color image, unfiltered scanlines — fine as a placeholder
    featured image for smoke tests; upgrade when real image generation lands.
    """
    row = b"\xff\xaa\x44\x00" * width  # RGBA, one row of pixels
    scanlines = b"".join(b"\x00" + row for _ in range(height))

    compressor = compressobj(6, zlib.DEFLATED, -15)
    compressed = compressor.compress(scanlines) + compressor.flush()

    def chunk(kind: str, data: bytes) -> bytes:
        raw = kind.encode("ascii") + data
        return (
            len(data).to_bytes(4, "big")
            + raw
            + (crc32(raw) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"  # 8-bit, RGBA, deflate, filter 0, no interlace
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk("IHDR", ihdr)
        + chunk("IDAT", compressed)
        + chunk("IEND", b"")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WordPress integration smoke test (Phase 1)"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="publish the test post instead of leaving it as draft",
    )
    parser.add_argument(
        "--generate-topic",
        action="store_true",
        help="generate and select a blog topic (Phase 2) instead of the WP smoke test",
    )
    parser.add_argument(
        "--research",
        type=int,
        metavar="TOPIC_ID",
        default=None,
        help="research a topic by id (Phase 3)",
    )
    parser.add_argument(
        "--run-cycle",
        action="store_true",
        help="run the full publish cycle (Phase 7): topic → research → "
        "content → validate → image → publish",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings()
    except Exception as exc:  # pydantic.ValidationError, missing env, etc.
        logger.error("Configuration error: %s", exc)
        logger.error(
            "Copy .env.example to .env and fill in your WordPress credentials."
        )
        return 2

    if args.generate_topic:
        from .topic_generator import TopicGenerator

        generator = TopicGenerator(settings)
        topic = generator.select_topic()
        logger.info(
            "Selected topic id=%s topic=%r category=%s status=%s",
            topic.id,
            topic.topic,
            topic.category,
            topic.status,
        )
        return 0

    if args.research is not None:
        from .providers.search import DuckDuckGoSearchProvider
        from .research import ResearchService

        provider = DuckDuckGoSearchProvider()
        service = ResearchService(settings, provider)
        result = service.research(args.research)
        logger.info(
            "Researched topic=%r category=%s sources=%d",
            result.topic,
            result.category,
            len(result.sources),
        )
        for source in result.sources:
            logger.info("  - %s (%s)", source.title, source.url)
        return 0

    if args.run_cycle:
        from .workflow import WorkflowOrchestrator

        orchestrator = WorkflowOrchestrator(settings)
        result = orchestrator.run_cycle(publish=args.publish)
        logger.info(
            "Cycle result: status=%s topic=%r post_id=%s",
            result.get("status"),
            result.get("topic"),
            result.get("post_id"),
        )
        if result.get("wp_url"):
            logger.info("Post URL: %s", result["wp_url"])
        if result.get("error"):
            logger.error("Cycle error: %s", result["error"])
        return 0

    client = WordPressClient(settings)

    try:
        categories = client.get_categories()
        logger.info(
            "Fetched %d categories: %s",
            len(categories),
            [category.name for category in categories[:5]],
        )

        tags = client.get_tags()
        logger.info("Fetched %d tags", len(tags))

        media = client.upload_media(
            file_bytes=_make_png(),
            file_name="smoke-test-featured.png",
            title="Smoke test featured image",
            alt_text="Smoke test placeholder",
        )
        logger.info("Uploaded media id=%s url=%s", media.id, media.source_url)

        category_ids = [categories[0].id] if categories else None
        post = client.create_post(
            title="Phase 1 smoke test post",
            content=(
                "This is a test post created by the WordPress blog automation "
                "Phase 1 smoke test."
            ),
            status="publish" if args.publish else settings.default_post_status,
            excerpt="Smoke test excerpt.",
            featured_media=media.id,
            categories=category_ids,
        )
        logger.info(
            "Created post id=%s status=%s link=%s",
            post.id,
            post.status,
            post.link,
        )

        fetched = client.get_post(post.id)
        logger.info(
            "Retrieved post id=%s title=%r",
            fetched.id,
            fetched.title_rendered,
        )

    except WordPressError as exc:
        logger.error(
            "WordPress error: %s (status=%s url=%s)",
            exc,
            exc.status_code,
            exc.url,
        )
        return 1

    logger.info("Smoke test complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
