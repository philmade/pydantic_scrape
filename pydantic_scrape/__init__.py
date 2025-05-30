"""
PydanticScrapeGraph - A clean, modular web scraping framework using pydantic-ai

This framework provides a clean alternative to ScrapeGraphAI, built on pydantic-ai's
graph architecture with camoufox for browser automation.

Key Features:
- Clean graph-based architecture using pydantic-ai
- Direct camoufox integration for browser automation
- Content type detection and specialized handlers
- Concurrent scraping support
- Type-safe state management
"""

from dotenv import load_dotenv

from .context import FetchResult, ScrapeContext, SourceType

load_dotenv()
__version__ = "0.1.0"
__all__ = [
    "scrape_url",
    "scrape_multiple_urls",
    "scrape_graph",
    "ScrapeContext",
    "FetchResult",
    "SourceType",
]
