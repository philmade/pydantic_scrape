"""
Dependencies for the pydantic scrape graph framework.

These dependencies handle the heavy lifting for scraping operations:
- FetchDependency: Content fetching and browser automation
- ContentAnalysisDependency: Content type detection and analysis 
- OpenAlexDependency: Academic paper metadata lookup
- CrossrefDependency: Academic paper reference lookup
"""

from .content_analysis import ContentAnalysisDependency, ContentAnalysisResult
from .crossref import CrossrefDependency, CrossrefResult
from .fetch import FetchDependency, FetchResult, Newspaper3kResult
from .openalex import OpenAlexDependency, OpenAlexResult
from .ai_scraper import AiScraperDependency
from .youtube import YouTubeDependency, YouTubeResult, YouTubeSubtitle
from .article import ArticleDependency, ArticleResult
from .document import DocumentDependency, DocumentResult

__all__ = [
    "FetchDependency",
    "FetchResult", 
    "Newspaper3kResult",
    "ContentAnalysisDependency",
    "ContentAnalysisResult",
    "OpenAlexDependency", 
    "OpenAlexResult",
    "CrossrefDependency",
    "CrossrefResult",
    "AiScraperDependency",
    "YouTubeDependency",
    "YouTubeResult",
    "YouTubeSubtitle",
    "ArticleDependency",
    "ArticleResult",
    "DocumentDependency",
    "DocumentResult",
]
