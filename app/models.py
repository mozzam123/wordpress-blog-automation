"""Pydantic models for the blog automation system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class TopicStatus(str, Enum):
    SELECTED = "SELECTED"
    RESEARCHED = "RESEARCHED"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class TopicBase(BaseModel):
    topic: str
    category: str


class TopicCreate(TopicBase):
    pass


class Topic(TopicBase):
    id: int
    status: TopicStatus
    created_at: datetime


class Source(BaseModel):
    title: str
    url: str
    snippet: str | None = None


class ResearchResult(BaseModel):
    topic: str
    category: str
    sources: list[Source]
    key_facts: list[str] = []
    books: list[dict[str, str]] = []


class FaqItem(BaseModel):
    question: str
    answer: str


class Section(BaseModel):
    heading: str
    subheadings: list[str] = []
    content: str
    # Per-book fields (optional; used when the section is a book entry)
    author: str | None = None
    genre: str | None = None
    page_count: str | None = None
    product_link: str | None = None
    cover_image: str | None = None
    hook: str | None = None
    perfect_for: str | None = None


class BlogContent(BaseModel):
    title: str
    seo_title: str
    slug: str
    meta_description: str
    focus_keyword: str
    introduction: str
    quick_pick: list[str] = []
    sections: list[Section]
    faq: list[FaqItem] = []
    conclusion: str
    cta_link: str = ""
    categories: list[str] = []
    tags: list[str] = []
    excerpt: str = ""
    sources: list[str] = []


class ValidationResult(BaseModel):
    passed: bool
    issues: list[str] = []
    score: int = 0
