"""Featured image service — Phase 6.

Generates a relevant featured image and uploads it to WordPress.
Uses Pollinations.ai (free, no API key required) for image generation.
"""

from __future__ import annotations

import logging
import urllib.parse

import requests

from .config import Settings
from .wordpress import WordPressClient

logger = logging.getLogger(__name__)


class ImageService:
    """Generates and uploads featured images to WordPress."""

    def __init__(self, settings: Settings, wp_client: WordPressClient) -> None:
        self.settings = settings
        self.wp_client = wp_client

    def generate_and_upload(self, prompt: str) -> int | None:
        """Generate an image and upload to WordPress. Returns media ID or None."""
        try:
            encoded_prompt = urllib.parse.quote(prompt)
            image_url = (
                f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                f"?width=1200&height=630&nologo=true"
            )

            response = requests.get(image_url, timeout=90)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "image/png")

            media = self.wp_client.upload_media(
                file_bytes=response.content,
                file_name="featured-image.png",
                mime_type=content_type,
                title="Featured Image",
                alt_text=prompt[:100],
            )
            logger.info("Featured image uploaded: media_id=%s", media.id)
            return media.id
        except Exception as exc:
            logger.error("Image generation/upload failed: %s", exc)
            return None
