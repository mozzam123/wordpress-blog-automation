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


class Section(BaseModel):
    heading: str
    subheadings: list[str] = []
    content: str


class BlogContent(BaseModel):
    title: str
    seo_title: str
    slug: str
    meta_description: str
    focus_keyword: str
    introduction: str
    sections: list[Section]
    conclusion: str
    categories: list[str] = []
    tags: list[str] = []
    excerpt: str = ""
    sources: list[str] = []


class ValidationResult(BaseModel):
    passed: bool
    issues: list[str] = []
    score: int = 0
