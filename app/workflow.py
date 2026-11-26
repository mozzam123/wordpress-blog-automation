"""Workflow orchestrator — Phase 7.

Connects topic generation, research, content generation, validation,
image generation, and WordPress publishing into one sequential workflow.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import Settings
from .database import (
    create_post_record,
    db_session,
    get_pending_topic,
    get_topic,
    update_post_record,
    update_topic_status,
)
from .models import BlogContent, ResearchResult, Source, TopicStatus
from .topic_generator import TopicGenerator
from .research import ResearchService
from .providers.search import DuckDuckGoSearchProvider
from .content import ContentGenerator
from .validator import SEOValidator
from .image import ImageService
from .wordpress import WordPressClient

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Runs the full weekly publishing cycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.wp_client = WordPressClient(settings)
        self.topic_generator = TopicGenerator(settings)
        self.search_provider = DuckDuckGoSearchProvider()
        self.research_service = ResearchService(settings, self.search_provider)
        self.content_generator = ContentGenerator(settings)
        self.validator = SEOValidator()
        self.image_service = ImageService(settings, self.wp_client)

    def run_cycle(self, publish: bool = True) -> dict:
        """Execute the full pipeline: topic → research → content → validate → image → publish."""
        result: dict = {"topic": None, "status": "failed", "post_id": None, "error": None}

        try:
            with db_session(self.settings) as conn:
                # Step 1: Get or select a topic
                topic_row = get_pending_topic(conn)
                if not topic_row:
                    logger.info("No pending topic — generating a new one")
                    new_topic = self.topic_generator.select_topic()
                    topic_row = {
                        "id": new_topic.id,
                        "topic": new_topic.topic,
                        "category": new_topic.category,
                        "status": new_topic.status.value,
                    }
                else:
                    topic_row = dict(topic_row)

                topic_id = topic_row["id"]
                result["topic"] = topic_row["topic"]
                logger.info("Working on topic id=%s: %s", topic_id, topic_row["topic"])

                # Step 2: Research (if not yet researched)
                if topic_row["status"] == TopicStatus.SELECTED.value:
                    research = self.research_service.research(topic_id)
                    logger.info("Research complete: %d sources", len(research.sources))
                else:
                    research = ResearchResult(
                        topic=topic_row["topic"],
                        category=topic_row["category"],
                        sources=[],
                        key_facts=[],
                        books=[],
                    )

                # Step 3: Generate content (if not yet generated)
                if topic_row["status"] in (
                    TopicStatus.SELECTED.value,
                    TopicStatus.RESEARCHED.value,
                ):
                    content = self.content_generator.generate(
                        topic_row["topic"], topic_row["category"], research
                    )
                    update_topic_status(conn, topic_id, TopicStatus.GENERATED)
                    logger.info("Content generated: %s", content.title)
                else:
                    # Content already generated — re-generate for simplicity
                    content = self.content_generator.generate(
                        topic_row["topic"], topic_row["category"], research
                    )
                    update_topic_status(conn, topic_id, TopicStatus.GENERATED)
                    logger.info("Content regenerated: %s", content.title)

                # Step 4: Validate
                validation = self.validator.validate(content)
                if not validation.passed:
                    issues = "; ".join(validation.issues)
                    logger.error("Validation failed: %s", issues)
                    update_topic_status(conn, topic_id, TopicStatus.FAILED)
                    create_post_record(
                        conn,
                        topic_id=topic_id,
                        title=content.title,
                        content=content.introduction,
                        seo_title=content.seo_title,
                        meta_description=content.meta_description,
                        status=TopicStatus.FAILED,
                        error_message=issues,
                    )
                    result["status"] = "failed"
                    result["error"] = issues
                    return result

                update_topic_status(conn, topic_id, TopicStatus.VALIDATED)
                logger.info("Validation passed (score=%d)", validation.score)

                # Step 5: Generate featured image
                image_prompt = (
                    f"Simple, clean, fresh book blog featured image for: {content.title}, "
                    f"an open book with fresh green leaves, bright natural daylight, "
                    f"minimal white background, bright and inviting, book lover aesthetic"
                )
                featured_media_id = self.image_service.generate_and_upload(image_prompt)

                # Step 6: Publish to WordPress
                # Resolve category names to WordPress category IDs so posts are
                # filed under the right category instead of defaulting to
                # "Uncategorized". Always include the "blog" category if it exists.
                wp_categories = self.wp_client.get_categories()
                name_to_id = {cat.name.lower(): cat.id for cat in wp_categories}
                category_ids = [
                    name_to_id[name.lower()]
                    for name in content.categories
                    if name.lower() in name_to_id
                ]
                blog_id = name_to_id.get("blog")
                if blog_id is not None and blog_id not in category_ids:
                    category_ids.append(blog_id)

                status = "publish" if publish else self.settings.default_post_status
                wp_post = self.wp_client.create_post(
                    title=content.title,
                    content=self._format_html(content),
                    status=status,
                    excerpt=content.excerpt,
                    featured_media=featured_media_id,
                    categories=category_ids,
                )

                update_topic_status(conn, topic_id, TopicStatus.PUBLISHED)
                create_post_record(
                    conn,
                    topic_id=topic_id,
                    title=content.title,
                    content=content.introduction,
                    seo_title=content.seo_title,
                    meta_description=content.meta_description,
                    featured_image_id=featured_media_id,
                    wordpress_post_id=wp_post.id,
                    status=TopicStatus.PUBLISHED,
                    published_at=datetime.now(timezone.utc),
                )

                result["status"] = "published"
                result["post_id"] = wp_post.id
                result["wp_url"] = wp_post.link
                logger.info("Post published: id=%s url=%s", wp_post.id, wp_post.link)

        except Exception as exc:
            logger.exception("Workflow failed: %s", exc)
            result["error"] = str(exc)

        return result

    def _format_html(self, content: BlogContent) -> str:
        """Convert structured content to HTML for WordPress.

        Structure:
          H1 title
          intro paragraph
          optional quick-pick list
          per-book H2 sections (hook, "Perfect for...", genre/pages/store link,
          cover image, body, optional H3 sub-sections)
          FAQ block (Q&A pairs)
          conclusion + CTA link
        """
        parts = [f"<h1>{content.title}</h1>"]
        parts.append(f"<p>{content.introduction}</p>")

        if content.quick_pick:
            parts.append("<h2>Quick Pick</h2>")
            parts.append("<ul>")
            for item in content.quick_pick:
                parts.append(f"<li>{item}</li>")
            parts.append("</ul>")

        for section in content.sections:
            parts.append(f"<h2>{section.heading}</h2>")
            if section.hook:
                parts.append(f"<p>{section.hook}</p>")
            if section.perfect_for:
                parts.append(
                    f"<p><strong>Perfect for readers who like...</strong> "
                    f"{section.perfect_for}</p>"
                )
            meta_bits = []
            if section.genre:
                meta_bits.append(f"<strong>Genre:</strong> {section.genre}")
            if section.page_count:
                meta_bits.append(f"<strong>Pages:</strong> {section.page_count}")
            if section.product_link:
                meta_bits.append(
                    f'<strong>Store:</strong> <a href="{section.product_link}">'
                    f"Buy on our store</a>"
                )
            if meta_bits:
                parts.append(f"<p>{' | '.join(meta_bits)}</p>")
            if section.cover_image:
                parts.append(
                    f'<img src="{section.cover_image}" '
                    f'alt="{section.heading} cover" '
                    f'style="max-width:100%;height:auto;display:block;margin:1em 0;">'
                )
            if section.content:
                parts.append(f"<p>{section.content}</p>")
            for sub in section.subheadings:
                parts.append(f"<h3>{sub}</h3>")

        if content.faq:
            parts.append("<h2>FAQ</h2>")
            for item in content.faq:
                parts.append(f"<h3>{item.question}</h3>")
                parts.append(f"<p>{item.answer}</p>")

        parts.append(f"<h2>Conclusion</h2>")
        parts.append(f"<p>{content.conclusion}</p>")
        if content.cta_link:
            collection = content.categories[0] if content.categories else "collection"
            parts.append(
                f'<p><a href="{content.cta_link}">Browse all {collection}</a></p>'
            )

        return "\n".join(parts)
