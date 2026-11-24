"""Application configuration loaded from environment.

Values come from the environment or a ``.env`` file. Real credentials must
never be committed — copy ``.env.example`` to ``.env`` and fill it in
locally.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """WordPress integration settings.

    Environment variables use the ``WP_`` prefix, e.g. ``WP_SITE_URL``.
    """

    site_url: str
    username: str
    app_password: str
    request_timeout: int = 30
    max_retries: int = 3
    default_post_status: str = "draft"
    db_path: str = "blog_automation.db"
    groq_api_key: str | None = None
    groq_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="WP_",
    )
