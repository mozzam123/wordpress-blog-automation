"""Search provider interface and implementations — Phase 3.

A replaceable web research/search provider. The default implementation uses
DuckDuckGo's HTML endpoint, which requires no API key. Swap in another
provider by subclassing :class:`BaseSearchProvider`.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

import requests

from ..models import Source

logger = logging.getLogger(__name__)


class BaseSearchProvider(ABC):
    """Replaceable search provider interface."""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[Source]:
        """Return search results for a query."""


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """Free DuckDuckGo HTML search (no API key required)."""

    BASE_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "wordpress-blog-automation/1.0"})

    def search(self, query: str, limit: int = 10) -> list[Source]:
        try:
            response = self.session.get(
                self.BASE_URL,
                params={"q": query},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Search request failed for %r: %s", query, exc)
            return []

        return self._parse_results(response.text, limit)

    def _parse_results(self, html: str, limit: int) -> list[Source]:
        sources: list[Source] = []
        blocks = re.findall(
            r'<div class="result[^"]*".*?</div>\s*</div>', html, re.DOTALL
        )
        for block in blocks[:limit]:
            title_match = re.search(
                r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not title_match:
                continue
            url = title_match.group(1)
            title = re.sub(r"<[^>]+>", "", title_match.group(2)).strip()
            snippet_match = re.search(
                r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL
            ) or re.search(
                r'<div class="result__snippet"[^>]*>(.*?)</div>', block, re.DOTALL
            )
            snippet = (
                re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
                if snippet_match
                else None
            )
            sources.append(Source(title=title, url=url, snippet=snippet))
        return sources
