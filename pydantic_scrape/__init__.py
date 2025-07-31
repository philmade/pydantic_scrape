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

from .dependencies.fetch import FetchResult

load_dotenv()
__version__ = "0.2.2"

# Core exports - always available
__all__ = [
    "FetchResult",
]

# Optional service imports - only imported when needed
def get_download_service():
    """Get DownloadService with graceful error handling for missing dependencies."""
    try:
        from .services.download_service import DownloadService
        return DownloadService
    except ImportError as e:
        raise ImportError(
            "DownloadService requires yt-dlp. Install with: pip install pydantic-scrape[youtube]"
        ) from e

def get_transcription_service():
    """Get TranscriptionService with graceful error handling for missing dependencies."""
    try:
        from .services.transcription_service import TranscriptionService, TranscriptionResult
        return TranscriptionService, TranscriptionResult
    except ImportError as e:
        raise ImportError(
            "TranscriptionService requires openai. Install with: pip install pydantic-scrape[ai]"
        ) from e
