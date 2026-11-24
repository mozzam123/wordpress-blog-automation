# WordPress Blog Automation — Phase 1: WordPress Integration

WordPress REST API client for the blog automation system. This phase covers:

- Application Password authentication
- Fetching categories and tags
- Uploading media (featured images)
- Creating and retrieving posts

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your WordPress site URL, username and Application Password
```

## Run the smoke test

```bash
python -m app.main
```

The test post is created as a **draft** by default. To publish it live, pass
`--publish` — only with explicit approval:

```bash
python -m app.main --publish
```

## What it does

1. Reads settings from ``.env`` (never committed).
2. Lists categories and tags.
3. Uploads a tiny placeholder PNG as media.
4. Creates a post (draft unless ``--publish``) with the media as featured image.
5. Fetches the created post back and logs its details.

Errors from the WordPress API raise ``WordPressError`` with the HTTP status
code, response body and request URL, and are logged. Transient failures
(429, 500, 502, 503, 504) are retried with backoff.

## Notes

- Category/tag listing fetches the first page only (``per_page=100``).
- Test posts default to draft status so nothing is published live by accident.
- No content is published to the live site without explicit approval.
