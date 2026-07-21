"""knowledge-scout extractors — v4.0 (2026-07-20)

Unified collection layer: RSSHub public instance + direct RSS feeds.
Replaces the previous 9 hand-written per-platform extractors.

Usage:
    from scripts.extract.collector import Collector
    c = Collector()
    articles = c.fetch_all()  # -> list[Article]
"""

from .collector import Collector, Article, SOURCES
