"""News/RSS feeds — Google News, custom RSS/Atom feeds.

Requires feedparser (included in base install).
"""

from __future__ import annotations

from sports_skills.news._connector import (
    fetch_feed as _fetch_feed,
)
from sports_skills.news._connector import (
    fetch_items as _fetch_items,
)


def _req(**kwargs):
    """Build request_data dict from kwargs."""
    return {"params": {k: v for k, v in kwargs.items() if v is not None}}


def fetch_feed(
    *,
    google_news: bool = False,
    query: str | None = None,
    url: str | None = None,
    language: str = "en-US",
    country: str = "US",
    after: str | None = None,
    before: str | None = None,
    sort_by_date: bool = False,
) -> dict:
    """Fetch and parse an RSS/Atom feed.

    Args:
        google_news: If True, use Google News RSS. Requires query unless url is provided.
        query: Search query for Google News. If query is provided without url, Google News mode is used automatically.
        url: RSS feed URL (required if google_news=False).
        language: Language code for Google News (default: "en-US").
        country: Country code for Google News (default: "US").
        after: Filter articles after this date (YYYY-MM-DD).
        before: Filter articles before this date (YYYY-MM-DD).
        sort_by_date: Sort entries by publication date (newest first).
    """
    return _fetch_feed(
        _req(
            google_news=google_news,
            query=query,
            url=url,
            language=language,
            country=country,
            after=after,
            before=before,
            sort_by_date=sort_by_date,
        )
    )


def fetch_items(
    *,
    google_news: bool = False,
    query: str | None = None,
    url: str | None = None,
    limit: int | None = None,
    language: str = "en-US",
    country: str = "US",
    after: str | None = None,
    before: str | None = None,
    sort_by_date: bool = False,
) -> dict:
    """Fetch items from an RSS/Atom feed, optionally limited by count.

    Args:
        google_news: If True, use Google News RSS. Requires query unless url is provided.
        query: Search query for Google News. If query is provided without url, Google News mode is used automatically.
        url: RSS feed URL (required if google_news=False).
        limit: Max number of items to return.
        language: Language code for Google News (default: "en-US").
        country: Country code for Google News (default: "US").
        after: Filter articles after this date (YYYY-MM-DD).
        before: Filter articles before this date (YYYY-MM-DD).
        sort_by_date: Sort entries by publication date (newest first).
    """
    return _fetch_items(
        _req(
            google_news=google_news,
            query=query,
            url=url,
            limit=limit,
            language=language,
            country=country,
            after=after,
            before=before,
            sort_by_date=sort_by_date,
        )
    )
