"""Research service — Phase 3.

Researches a selected topic using a replaceable search provider, collects
facts and source URLs, and updates the topic status to RESEARCHED so the
content generator (Phase 4) can consume it.
"""

from __future__ import annotations

from .config import Settings
from .database import db_session, get_topic, update_topic_status
from .models import ResearchResult, Source, TopicStatus
from .providers.search import BaseSearchProvider, DuckDuckGoSearchProvider


class ResearchService:
    """Researches a blog topic using a search provider."""

    def __init__(
        self,
        settings: Settings,
        search_provider: BaseSearchProvider | None = None,
    ) -> None:
        self.settings = settings
        self.search_provider = search_provider or DuckDuckGoSearchProvider(
            timeout=settings.request_timeout
        )

    def research(self, topic_id: int) -> ResearchResult:
        """Look up a topic by id, research it, and mark it RESEARCHED."""
        with db_session(self.settings) as conn:
            topic = get_topic(conn, topic_id)
            if not topic:
                raise ValueError(f"Topic {topic_id} not found")
            if topic["status"] != TopicStatus.SELECTED:
                raise ValueError(
                    f"Topic {topic_id} is not in SELECTED status "
                    f"(current: {topic['status']})"
                )

            query = topic["topic"]
            sources = self.search_provider.search(query, limit=10)

            key_facts = [s.snippet or s.title for s in sources if s.snippet or s.title]

            research = ResearchResult(
                topic=topic["topic"],
                category=topic["category"],
                sources=sources,
                key_facts=key_facts,
                books=[],
            )

            update_topic_status(conn, topic_id, TopicStatus.RESEARCHED)
            return research
