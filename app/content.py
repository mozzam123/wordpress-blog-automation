"""Content generator — Phase 4.

Uses Groq to generate structured blog content from research results.
"""

from __future__ import annotations

import json
import logging
import re
import time

import requests

from .config import Settings
from .models import BlogContent, ResearchResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds; wait doubles each retry


class ContentGenerator:
    """Generates structured blog content using Groq."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.groq_api_key
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required for content generation")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = settings.groq_model or "llama-3.1-8b-instant"

    def generate(
        self, topic: str, category: str, research: ResearchResult
    ) -> BlogContent:
        """Generate a complete blog post from research."""
        sources_text = "\n".join(
            f"- {s.title}: {s.url}" for s in research.sources[:10]
        )
        facts_text = "\n".join(f"- {f}" for f in research.key_facts[:10])

        prompt = f"""Write a complete, engaging blog post about: {topic}
Category: {category}

Research facts:
{facts_text if facts_text else "No specific facts provided."}

Source URLs:
{sources_text if sources_text else "No sources provided."}

Return ONLY a valid JSON object with these exact keys:
- title: compelling blog post title
- seo_title: SEO title under 60 characters
- slug: URL-friendly slug (lowercase, hyphens)
- meta_description: under 160 characters
- focus_keyword: primary SEO keyword
- introduction: 2-3 engaging paragraphs
- sections: array of objects with heading, subheadings[], content
- conclusion: concluding paragraph
- categories: array of category names (include "{category}")
- tags: array of relevant tags
- excerpt: short excerpt under 55 words
- sources: array of source URLs from the research above

Write for book lovers in British English. Use the focus keyword naturally. Make it informative and engaging."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert book blogger and SEO writer. Return only valid JSON, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    self.api_url, headers=headers, json=payload, timeout=90
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if (
                    attempt < MAX_RETRIES
                    and getattr(exc, "response", None) is not None
                    and exc.response.status_code in (429, 500, 502, 503, 504)
                ):
                    wait = BACKOFF_BASE ** attempt
                    logger.warning(
                        "Groq API returned %s, retrying in %ds (attempt %d/%d)",
                        exc.response.status_code,
                        wait,
                        attempt,
                        MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

        data = response.json()
        content_text = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.startswith("```"):
            content_text = content_text[3:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]
        content_text = content_text.strip()

        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError:
            # LLM output is often imperfect JSON. Try to repair common issues.
            repaired = _repair_json(content_text)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse Groq JSON response: %s", exc)
                logger.debug("Raw response: %s", content_text[:2000])
                raise

        parsed = _ensure_fields(parsed, topic, category)
        return BlogContent(**parsed)


def _make_slug(title: str) -> str:
    """Convert a title to a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def _ensure_fields(parsed: dict, topic: str, category: str) -> dict:
    """Fill in missing required fields with sensible defaults so the
    pipeline doesn't fail when Groq omits a key from its JSON response."""
    parsed.setdefault("title", topic)
    title = parsed["title"]
    parsed.setdefault("seo_title", title[:60])
    parsed.setdefault("slug", _make_slug(title))
    parsed.setdefault("meta_description", parsed.get("excerpt") or title[:160])
    parsed.setdefault("focus_keyword", (parsed.get("categories") or [category])[0] or category)
    parsed.setdefault("introduction", parsed.get("excerpt") or title)
    parsed.setdefault("sections", [])
    parsed.setdefault("conclusion", parsed.get("excerpt") or title)
    return parsed


def _repair_json(text: str) -> str:
    """Attempt to repair common LLM JSON formatting issues."""
    # Extract the outermost JSON object if extra text surrounds it
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # Quote unquoted property names after {, , }, or ]
    text = re.sub(r'([{,}]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    text = re.sub(r'(\]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)

    # Remove trailing commas before closing braces/brackets
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*\]", "]", text)

    # Replace single quotes with double quotes
    text = text.replace("'", '"')

    return text
