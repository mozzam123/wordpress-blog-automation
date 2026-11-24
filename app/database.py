"""SQLite database layer for the blog automation system."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import Settings
from .models import TopicStatus


def get_connection(settings: Settings) -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session(settings: Settings) -> Iterator[sqlite3.Connection]:
    """Provide a transactional scope around a series of operations."""
    conn = get_connection(settings)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(settings: Settings) -> None:
    """Create tables if they do not exist."""
    with db_session(settings) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blog_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'SELECTED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                title TEXT,
                content TEXT,
                seo_title TEXT,
                meta_description TEXT,
                featured_image_id INTEGER,
                wordpress_post_id INTEGER,
                status TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES blog_topics(id)
            );
            """
        )


def get_topic(conn: sqlite3.Connection, topic_id: int) -> dict | None:
    """Fetch a topic row by id."""
    row = conn.execute(
        "SELECT id, topic, category, status, created_at "
        "FROM blog_topics WHERE id = ?",
        (topic_id,),
    ).fetchone()
    return dict(row) if row else None


def update_topic_status(
    conn: sqlite3.Connection, topic_id: int, status: TopicStatus
) -> None:
    """Update a topic's status."""
    conn.execute(
        "UPDATE blog_topics SET status = ? WHERE id = ?",
        (status.value, topic_id),
    )


def get_pending_topic(conn: sqlite3.Connection) -> dict | None:
    """Return the first SELECTED topic, or None if none pending."""
    row = conn.execute(
        "SELECT id, topic, category, status, created_at "
        "FROM blog_topics WHERE status = 'SELECTED' ORDER BY id LIMIT 1",
    ).fetchone()
    return dict(row) if row else None


def create_post_record(
    conn: sqlite3.Connection,
    topic_id: int,
    title: str,
    content: str,
    seo_title: str | None = None,
    meta_description: str | None = None,
    featured_image_id: int | None = None,
    wordpress_post_id: int | None = None,
    status: TopicStatus | str | None = None,
    error_message: str | None = None,
    published_at: object | None = None,
) -> None:
    """Insert a post record linked to a topic."""
    conn.execute(
        """
        INSERT INTO blog_posts
            (topic_id, title, content, seo_title, meta_description,
             featured_image_id, wordpress_post_id, status, error_message,
             published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            topic_id,
            title,
            content,
            seo_title,
            meta_description,
            featured_image_id,
            wordpress_post_id,
            status.value if isinstance(status, TopicStatus) else status,
            error_message,
            published_at,
        ),
    )


def update_post_record(
    conn: sqlite3.Connection,
    topic_id: int,
    wordpress_post_id: int | None = None,
    status: TopicStatus | str | None = None,
    error_message: str | None = None,
) -> None:
    """Update an existing post record's fields."""
    fields = []
    params: list[object] = []
    if wordpress_post_id is not None:
        fields.append("wordpress_post_id = ?")
        params.append(wordpress_post_id)
    if status is not None:
        fields.append("status = ?")
        params.append(status.value if isinstance(status, TopicStatus) else status)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)
    if not fields:
        return
    params.append(topic_id)
    conn.execute(
        f"UPDATE blog_posts SET {', '.join(fields)} WHERE topic_id = ?",
        tuple(params),
    )
