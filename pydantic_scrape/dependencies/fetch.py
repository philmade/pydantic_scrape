"""Fetch dependency - handles content fetching via browser automation"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from camoufox.async_api import AsyncCamoufox
from loguru import logger
from newspaper import Article


@dataclass
class FetchResult:
    """Result from fetching content"""

    url: str
    content: Optional[str] = None
    title: Optional[str] = None
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    error: Optional[str] = None

    # Timing information
    fetch_duration: Optional[float] = None
    page_load_time: Optional[float] = None
    final_url: Optional[str] = None

    # Custom extracted data (from fetch_and_then_run)
    custom_data: Optional[Dict[str, Any]] = None


@dataclass
class Newspaper3kResult:
    """Result from newspaper3k article parsing - matches newspaper3k Article attributes"""

    # Core content
    title: Optional[str] = None
    text: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    top_image: Optional[str] = None

    # Metadata
    authors: List[str] = None
    publish_date: Optional[str] = None  # datetime as string
    keywords: List[str] = None
    meta_keywords: List[str] = None
    tags: List[str] = None

    # Images and media
    images: List[str] = None
    movies: List[str] = None

    # Article structure
    article_html: Optional[str] = None
    meta_description: Optional[str] = None
    meta_lang: Optional[str] = None
    meta_favicon: Optional[str] = None

    # Processing status
    is_parsed: bool = False
    download_state: int = 0  # 0=not downloaded, 1=downloaded, 2=failed
    download_exception_msg: Optional[str] = None

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.keywords is None:
            self.keywords = []
        if self.meta_keywords is None:
            self.meta_keywords = []
        if self.tags is None:
            self.tags = []
        if self.images is None:
            self.images = []
        if self.movies is None:
            self.movies = []


class FetchDependency:
    """
    Dependency for fetching web content using camoufox browser automation.

    This is a reusable service that any node can use for content fetching.
    """

    def __init__(self, timeout_ms: int = 30000, wait_for: str = "domcontentloaded"):
        self.timeout_ms = timeout_ms
        self.wait_for = wait_for

    async def fetch_content(
        self, url: str, browser_config: Optional[Dict] = None
    ) -> FetchResult:
        """
        Fetch content from URL using camoufox.

        Args:
            url: URL to fetch
            browser_config: Optional browser configuration for camoufox

        Returns:
            FetchResult with content or error information
        """
        if browser_config is None:
            browser_config = {"headless": True, "humanize": True}

        fetch_started = time.time()
        logger.info(f"FetchDependency: Fetching content from {url}")

        try:
            async with AsyncCamoufox(**browser_config) as browser:
                page = await browser.new_page()

                try:
                    page_load_start = time.time()

                    # Navigate to the URL
                    response = await page.goto(
                        url, timeout=self.timeout_ms, wait_until=self.wait_for
                    )

                    page_load_time = time.time() - page_load_start

                    # Extract content
                    html = await page.content()
                    title = await page.title()

                    # Create successful result
                    result = FetchResult(
                        url=url,
                        content=html,
                        title=title,
                        content_type=response.headers.get("content-type")
                        if response
                        else None,
                        status_code=response.status if response else None,
                        headers=dict(response.headers) if response else {},
                        fetch_duration=time.time() - fetch_started,
                        page_load_time=page_load_time,
                        final_url=page.url,
                    )

                    logger.info(
                        f"FetchDependency: Successfully fetched {len(html)} chars from {url}"
                    )
                    return result

                finally:
                    await page.close()

        except Exception as e:
            logger.error(f"FetchDependency: Error fetching {url}: {str(e)}")

            # Create error result
            return FetchResult(
                url=url, error=str(e), fetch_duration=time.time() - fetch_started
            )

    async def fetch_content_simple(self, url: str) -> FetchResult:
        """Simple fetch with default configuration"""
        return await self.fetch_content(url)

    async def fetch_and_then_run(
        self, url: str, browser_config: Optional[Dict] = None, custom_extract=None
    ) -> FetchResult:
        """
        Fetch content and then run custom extraction logic.

        Args:
            url: URL to fetch
            browser_config: Browser configuration
            custom_extract: Async function that takes (page) and returns dict of extracted data

        Returns:
            FetchResult with custom extracted data
        """
        if browser_config is None:
            browser_config = {"headless": True, "humanize": True}

        fetch_started = time.time()
        logger.info(f"FetchDependency: Fetching with custom extraction from {url}")

        try:
            async with AsyncCamoufox(**browser_config) as browser:
                page = await browser.new_page()

                try:
                    page_load_start = time.time()

                    # Navigate to the URL
                    response = await page.goto(
                        url, timeout=self.timeout_ms, wait_until=self.wait_for
                    )

                    page_load_time = time.time() - page_load_start

                    # Default content extraction
                    html = await page.content()
                    title = await page.title()

                    # Custom extraction if provided
                    custom_data = {}
                    if custom_extract:
                        try:
                            custom_data = await custom_extract(page)
                        except Exception as e:
                            logger.warning(f"Custom extraction failed: {e}")

                    # Create result with custom data
                    result = FetchResult(
                        url=url,
                        content=html,
                        title=title,
                        content_type=response.headers.get("content-type")
                        if response
                        else None,
                        status_code=response.status if response else None,
                        headers=dict(response.headers) if response else {},
                        fetch_duration=time.time() - fetch_started,
                        page_load_time=page_load_time,
                        final_url=page.url,
                    )

                    # Add custom extracted data to result
                    if custom_data:
                        result.custom_data = custom_data

                    logger.info(
                        f"FetchDependency: Successfully fetched {len(html)} chars with custom extraction"
                    )
                    return result

                finally:
                    await page.close()

        except Exception as e:
            logger.error(
                f"FetchDependency: Error fetching with custom extraction {url}: {str(e)}"
            )

            return FetchResult(
                url=url, error=str(e), fetch_duration=time.time() - fetch_started
            )

    def parse_with_newspaper3k(self, fetch_result: FetchResult) -> Newspaper3kResult:
        """
        Parse a FetchResult using newspaper3k to extract article content.

        Args:
            fetch_result: FetchResult containing HTML content

        Returns:
            Newspaper3kResult with parsed article data
        """
        if fetch_result.error or not fetch_result.content:
            return Newspaper3kResult(
                url=fetch_result.url,
                download_state=2,
                download_exception_msg=fetch_result.error or "No content available",
            )

        try:
            # Create newspaper3k Article object
            article = Article(fetch_result.url)

            # Set the HTML content directly (bypass download)
            article.set_html(fetch_result.content)
            article.parse()

            # Convert to our dataclass
            result = Newspaper3kResult(
                title=article.title,
                text=article.text,
                summary=article.summary if hasattr(article, "summary") else None,
                url=article.url,
                top_image=article.top_image,
                authors=list(article.authors) if article.authors else [],
                publish_date=article.publish_date.isoformat()
                if article.publish_date
                else None,
                keywords=list(article.keywords) if article.keywords else [],
                meta_keywords=list(article.meta_keywords)
                if article.meta_keywords
                else [],
                tags=list(article.tags) if article.tags else [],
                images=list(article.images) if article.images else [],
                movies=list(article.movies) if article.movies else [],
                article_html=article.article_html,
                meta_description=article.meta_description,
                meta_lang=article.meta_lang,
                meta_favicon=article.meta_favicon,
                is_parsed=True,
                download_state=1,
            )

            logger.info(
                f"FetchDependency: Successfully parsed article with newspaper3k: {article.title}"
            )
            return result

        except Exception as e:
            logger.error(f"FetchDependency: Error parsing with newspaper3k: {str(e)}")
            return Newspaper3kResult(
                url=fetch_result.url, download_state=2, download_exception_msg=str(e)
            )
