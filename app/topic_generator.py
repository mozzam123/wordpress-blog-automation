"""Topic generator — Phase 2.

Generates book-related blog topics based on the site niche, current date,
and previously published topics. Avoids duplicates by checking SQLite.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Optional

from .config import Settings
from .database import db_session, init_db
from .models import Topic, TopicStatus


class TopicGenerator:
    """Generates and selects a blog topic for the weekly cycle."""

    # Evergreen book topics usable any time of year.
    EVERGREEN_TOPICS: list[tuple[str, str]] = [
        ("Modern Classics Worth Reading", "Fiction"),
        ("Underrated Novels and Hidden Gems", "Fiction"),
        ("The Best Debut Novels of the Year", "Fiction"),
        ("Upcoming Book Adaptations to Watch", "Fiction"),
        ("Book-to-Screen Adaptations: The Good and the Bad", "Fiction"),
        ("How to Build a Reading Habit", "Non-Fiction"),
        ("Best Literary Fiction of the Decade", "Fiction"),
        ("Must-Read Memoirs and Autobiographies", "Non-Fiction"),
        ("Essential Non-Fiction Books Everyone Should Read", "Non-Fiction"),
        ("Book Club Picks for Lively Discussion", "Fiction"),
    ]

    # Seasonal topics keyed by month (1-12).
    SEASONAL_TOPICS: dict[int, list[tuple[str, str]]] = {
        12: [
            ("Best Books to Gift This Holiday Season", "Gifts"),
            ("Year-End Reading Roundup", "Fiction"),
        ],
        1: [
            ("New Year Reading Resolutions", "Non-Fiction"),
            ("Winter Reading List", "Fiction"),
        ],
        2: [
            ("Romance Novels for Valentine's Day", "Fiction"),
            ("Black History Month Reads", "Non-Fiction"),
        ],
        3: [
            ("Women's History Month Books", "Non-Fiction"),
            ("Spring Reading List", "Fiction"),
        ],
        4: [
            ("Poetry Month Collections", "Fiction"),
            ("Spring Non-Fiction Releases", "Non-Fiction"),
        ],
        5: [
            ("Summer Beach Reads", "Fiction"),
            ("Memoirs for Summer Reading", "Non-Fiction"),
        ],
        6: [
            ("Pride Month LGBTQ+ Books", "Fiction"),
            ("Mid-Year Reading Roundup", "Fiction"),
        ],
        7: [
            ("Summer Blockbuster Books", "Fiction"),
            ("Beach Reads and Poolside Books", "Fiction"),
        ],
        8: [
            ("Back-to-School Reading List", "Non-Fiction"),
            ("Late Summer Reads", "Fiction"),
        ],
        9: [
            ("Fall Reading List", "Fiction"),
            ("Book Awards Season Contenders", "Fiction"),
        ],
        10: [
            ("Spooky Reads for Halloween", "Fiction"),
            ("Cozy Autumn Books", "Fiction"),
        ],
        11: [
            ("Thanksgiving and Gratitude Reads", "Non-Fiction"),
            ("Best Books of the Year So Far", "Fiction"),
        ],
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        init_db(settings)

    def _candidate_topics(self) -> list[tuple[str, str]]:
        """Build the pool of topic candidates for the current date/week."""
        now = dt.datetime.now()
        candidates = list(self.EVERGREEN_TOPICS)
        candidates.extend(self.SEASONAL_TOPICS.get(now.month, []))
        # Stable per ISO week so the same topic isn't re-picked mid-week,
        # but varies from week to week within the same month.
        random.seed(now.isocalendar()[1])
        random.shuffle(candidates)
        return candidates

    def _is_duplicate(self, conn, topic: str) -> bool:
        """Return True if the topic already exists in the database."""
        row = conn.execute(
            "SELECT 1 FROM blog_topics WHERE topic = ?", (topic,)
        ).fetchone()
        return row is not None

    def select_topic(self) -> Topic:
        """Pick a non-duplicate topic, store it as SELECTED, and return it."""
        with db_session(self.settings) as conn:
            for topic, category in self._candidate_topics():
                if not self._is_duplicate(conn, topic):
                    cur = conn.execute(
                        "INSERT INTO blog_topics (topic, category, status) "
                        "VALUES (?, ?, ?)",
                        (topic, category, TopicStatus.SELECTED),
                    )
                    topic_id = cur.lastrowid
                    row = conn.execute(
                        "SELECT id, topic, category, status, created_at "
                        "FROM blog_topics WHERE id = ?",
                        (topic_id,),
                    ).fetchone()
                    return Topic.model_validate(dict(row))
            raise RuntimeError("No unused topics available this cycle")
