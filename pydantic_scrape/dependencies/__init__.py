"""
Dependencies for the pydantic scrape graph framework.

These dependencies handle the heavy lifting for scraping operations:
- FetchDependency: Content fetching and browser automation
- ContentAnalysisDependency: Content type detection and analysis
- OpenAlexDependency: Academic paper metadata lookup
- CrossrefDependency: Academic paper reference lookup
- VideoDependency: Complete video processing pipeline (transcription, editing, rendering)
"""

from .ai_scraper import AiScraperDependency
from .article import ArticleDependency, ArticleResult
from .content_analysis import ContentAnalysisDependency, ContentAnalysisResult
from .crossref import CrossrefDependency, CrossrefResult
from .document import DocumentDependency, DocumentResult
from .fetch import FetchDependency, FetchResult, Newspaper3kResult, SmartFetchResult
from .openalex import OpenAlexDependency, OpenAlexResult

__all__ = [
    "FetchDependency",
    "FetchResult",
    "Newspaper3kResult",
    "SmartFetchResult",
    "ContentAnalysisDependency",
    "ContentAnalysisResult",
    "OpenAlexDependency",
    "OpenAlexResult",
    "CrossrefDependency",
    "CrossrefResult",
    "AiScraperDependency",
    "ArticleDependency",
    "ArticleResult",
    "DocumentDependency",
    "DocumentResult",
    # Consolidated video processing
]
