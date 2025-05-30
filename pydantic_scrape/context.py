"""
ScrapeContext - Clean state management for the pydantic-ai scraping graph
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .dependencies.fetch import FetchResult


class SourceType(str, Enum):
    """Source type classification"""

    SCIENCE = "SCIENCE"
    DOC = "DOC"
    YOUTUBE = "YOUTUBE"
    TWEET = "TWEET"
    OTHER = "OTHER"


class ScienceMetadata(BaseModel):
    """Science-specific metadata from OpenAlex lookup"""

    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    title_match_score: Optional[float] = None
    match_method: Optional[str] = None  # "doi_exact", "title_fuzzy", "none"
    authors: List[str] = field(default_factory=list)
    journal_name: Optional[str] = None
    publication_date: Optional[str] = None
    open_access: bool = False
    full_text_links: List[Dict[str, Any]] = field(default_factory=list)
    primary_location: Optional[Dict[str, Any]] = None
    citation_count: Optional[int] = None
    raw_openalex_data: Optional[Dict[str, Any]] = None

    # Content extraction
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    # Full text processing results
    full_text_fetched: bool = False
    full_text_source: Optional[str] = None  # "pdf", "html", "xml"
    full_text_url: Optional[str] = None


@dataclass
class ScrapeContext:
    """
    Central state management for the scraping graph.
    Clean, single-responsibility state container.
    """

    # Input
    url: str

    # Fetched content
    fetch_result: Optional[FetchResult] = None

    # Content analysis
    detected_source_type: Optional[SourceType] = None
    content_metadata: Dict[str, Any] = field(default_factory=dict)

    # Processing state
    current_stage: str = "initialized"
    completed_stages: List[str] = field(default_factory=list)

    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # Configuration (for camoufox)
    browser_config: Dict[str, Any] = field(
        default_factory=lambda: {"headless": True, "humanize": True}
    )

    # Performance tracking
    start_time: datetime = field(default_factory=datetime.now)

    def add_error(self, stage: str, error: Exception, details: Optional[Dict] = None):
        """Add an error to the context with structured information"""
        error_info = {
            "stage": stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now(),
            "details": details or {},
        }
        self.errors.append(error_info)

    def complete_stage(self, stage: str):
        """Mark a processing stage as completed"""
        self.completed_stages.append(stage)
        self.current_stage = stage

    def has_errors(self) -> bool:
        """Check if any errors occurred during processing"""
        return len(self.errors) > 0

    def get_processing_time(self) -> float:
        """Get total processing time in seconds"""
        return (datetime.now() - self.start_time).total_seconds()
