"""WordPress REST API client — Phase 1: WordPress integration.

Contract (WordPress REST API, ``wp-json/wp/v2``):

  Authentication: Application Password ->
      ``Authorization: Basic base64(username:app_password)``
  GET    /categories           list categories
  GET    /tags                 list tags
  POST   /media                upload an image (multipart ``file`` field)
  POST   /posts                create a post (JSON body)
  GET    /posts/{id}           retrieve a single post

All credentials come from :class:`app.config.Settings` and are never
hardcoded. Failed responses raise :class:`WordPressError` with the HTTP
status code, response body and request URL so callers can log and retry.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import requests
from pydantic import BaseModel, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings

logger = logging.getLogger(__name__)


class WordPressError(Exception):
    """Raised when the WordPress REST API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.url = url


class Category(BaseModel):
    id: int
    name: str
    slug: str
    count: int = 0


class Tag(BaseModel):
    id: int
    name: str
    slug: str
    count: int = 0


class MediaResponse(BaseModel):
    id: int
    source_url: str
    mime_type: str | None = None


class PostResponse(BaseModel):
    id: int
    link: str
    status: str
    title: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    excerpt: dict[str, Any] = Field(default_factory=dict)
    date: str | None = None
    categories: list[int] = Field(default_factory=list)
    tags: list[int] = Field(default_factory=list)
    featured_media: int = 0

    @property
    def title_rendered(self) -> str:
        return self.title.get("rendered", "") if isinstance(self.title, dict) else ""


class WordPressClient:
    """Thin client around the WordPress REST API with retries and errors."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        base = settings.site_url.rstrip("/")
        self.api_base = f"{base}/wp-json/wp/v2"

        token = base64.b64encode(
            f"{settings.username}:{settings.app_password}".encode()
        ).decode("ascii")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Basic {token}",
                "User-Agent": "wordpress-blog-automation/1.0",
            }
        )

        retry = Retry(
            total=settings.max_retries,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(
                ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
            ),
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    # ------------------------------------------------------------------ request

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any:
        url = f"{self.api_base}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                files=files,
                timeout=self.settings.request_timeout,
            )
        except requests.RequestException as exc:
            logger.error("WordPress request failed: %s %s -> %s", method, url, exc)
            raise WordPressError(str(exc), url=url) from exc

        if not response.ok:
            body = response.text[:500]
            logger.error(
                "WordPress API error: %s %s -> HTTP %s: %s",
                method,
                url,
                response.status_code,
                body,
            )
            raise WordPressError(
                f"WordPress API returned HTTP {response.status_code}",
                status_code=response.status_code,
                response_text=body,
                url=url,
            )

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # ------------------------------------------------------------ categories/tags

    def get_categories(self, per_page: int = 100) -> list[Category]:
        """Return the site's categories (first page only)."""
        data = self._request("GET", "categories", params={"per_page": per_page})
        return [Category.model_validate(item) for item in (data or [])]

    def get_tags(self, per_page: int = 100) -> list[Tag]:
        """Return the site's tags (first page only)."""
        data = self._request("GET", "tags", params={"per_page": per_page})
        return [Tag.model_validate(item) for item in (data or [])]

    # ------------------------------------------------------------------- media

    def upload_media(
        self,
        *,
        file_path: str | None = None,
        file_name: str | None = None,
        file_bytes: bytes | None = None,
        mime_type: str = "image/png",
        title: str | None = None,
        alt_text: str | None = None,
    ) -> MediaResponse:
        """Upload an image to the media library.

        Either ``file_path`` or ``file_bytes`` must be given. Returns the media
        object; its ``id`` can be assigned as a post's ``featured_media``.
        """
        if file_bytes is None:
            if file_path is None:
                raise ValueError("provide file_path or file_bytes")
            with open(file_path, "rb") as handle:
                file_bytes = handle.read()
            file_name = file_name or file_path.rsplit("/", 1)[-1]

        files = {"file": (file_name or "upload", file_bytes, mime_type)}
        data: dict[str, str] = {}
        if title:
            data["title"] = title
        if alt_text:
            data["alt_text"] = alt_text

        response = self._request("POST", "media", data=data, files=files)
        return MediaResponse.model_validate(response)

    # -------------------------------------------------------------------- posts

    def create_post(
        self,
        *,
        title: str,
        content: str,
        status: str | None = None,
        categories: list[int] | None = None,
        tags: list[int] | None = None,
        featured_media: int | None = None,
        excerpt: str | None = None,
        slug: str | None = None,
    ) -> PostResponse:
        """Create a post.

        Defaults to :attr:`Settings.default_post_status` (draft) so experimental
        content is never published to the live site by accident.
        """
        if status is None:
            status = self.settings.default_post_status

        payload: dict[str, Any] = {"title": title, "content": content, "status": status}
        if categories is not None:
            payload["categories"] = categories
        if tags is not None:
            payload["tags"] = tags
        if featured_media is not None:
            payload["featured_media"] = featured_media
        if excerpt is not None:
            payload["excerpt"] = excerpt
        if slug is not None:
            payload["slug"] = slug

        response = self._request("POST", "posts", json=payload)
        return PostResponse.model_validate(response)

    def update_post(self, post_id: int, **fields) -> PostResponse:
        """Update an existing post's fields (e.g. featured_media)."""
        response = self._request("POST", f"posts/{post_id}", json=fields)
        return PostResponse.model_validate(response)

    def get_post(self, post_id: int) -> PostResponse:
        """Return a single post by id."""
        response = self._request("GET", f"posts/{post_id}")
        return PostResponse.model_validate(response)
