"""
Dynamic scrape graph - AI-powered data extraction
"""

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from ..dependencies import (
    FetchDependency,
)
from ..dependencies.ai_scraper import AiScraperDependency


async def scrape_with_ai(
    url: str,
    output_type: Type[BaseModel],
    extraction_prompt: str,
    browser_config: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    AI-powered scraping using the dependency pattern.

    Args:
        url: URL to scrape
        output_type: Pydantic model type to extract into
        extraction_prompt: What data to extract
        browser_config: Optional browser configuration
    """

    # Dependencies do the heavy lifting
    fetch_dep = FetchDependency(timeout_ms=30000)
    ai_scraper_dep = AiScraperDependency()

    # Fetch content
    fetch_result = await fetch_dep.fetch_content(
        url, browser_config or {"headless": True, "humanize": True}
    )

    if fetch_result.error:
        return {"error": fetch_result.error, "url": url}

    # Extract with AI
    extracted_data = await ai_scraper_dep.extract_data(
        fetch_result=fetch_result,
        output_type=output_type,
        extraction_prompt=extraction_prompt,
    )

    # Compose final result
    final_result = {
        "url": fetch_result.url,
        "title": fetch_result.title,
        "status_code": fetch_result.status_code,
        "content_length": len(fetch_result.content or ""),
        "fetch_duration": fetch_result.fetch_duration,
        # AI extraction results
        "extracted_data": extracted_data.model_dump(),
        "extraction_config": {
            "output_type": output_type.__name__,
            "extraction_prompt": extraction_prompt,
        },
    }

    return final_result


# Export
__all__ = ["scrape_with_ai"]
