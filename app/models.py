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
