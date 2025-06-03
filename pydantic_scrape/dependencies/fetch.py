"""Fetch dependency - handles content fetching via browser automation"""

import os
import time
import httpx
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

    async def fetch_smart_content(
        self, url: str, browser_config: Optional[Dict] = None, base_url: Optional[str] = None
    ) -> "SmartFetchResult":
        """
        Smart content fetching that handles PDFs, HTML articles, and other formats.
        
        This method:
        1. Follows redirects using browser automation
        2. Detects content type from final URL and headers
        3. Downloads binary content for PDFs using direct HTTP
        4. Parses HTML articles using newspaper3k
        5. Returns clean text content appropriate for the type
        
        Args:
            url: URL to fetch (may be PDF, HTML article, or other)
            browser_config: Optional browser configuration
            base_url: Base URL for resolving relative URLs
            
        Returns:
            SmartFetchResult with detected content type and clean text
        """
        # Fix relative URLs
        if url.startswith('/') and base_url:
            from urllib.parse import urljoin
            url = urljoin(base_url, url)
            logger.info(f"FetchDependency: Resolved relative URL to: {url}")
        elif url.startswith('/') and not base_url:
            logger.error(f"FetchDependency: Relative URL {url} provided without base_url")
            return SmartFetchResult(
                url=url,
                error="Relative URL provided without base_url",
                fetch_duration=0,
                format="error"
            )
        
        logger.info(f"FetchDependency: Smart fetching content from {url}")
        
        if browser_config is None:
            browser_config = {"headless": True, "humanize": True}
        
        fetch_started = time.time()
        
        try:
            # Step 1: Use browser to follow redirects and detect final URL/content type
            async with AsyncCamoufox(**browser_config) as browser:
                page = await browser.new_page()
                
                try:
                    # Navigate and get final URL after redirects
                    response = await page.goto(
                        url, timeout=self.timeout_ms, wait_until=self.wait_for
                    )
                    
                    final_url = page.url
                    content_type = response.headers.get("content-type", "").lower() if response else ""
                    status_code = response.status if response else None
                    
                    logger.info(f"FetchDependency: Final URL after redirects: {final_url}")
                    logger.info(f"FetchDependency: Content-Type: {content_type}")
                    
                    # Step 2: Detect if this is likely a PDF
                    is_pdf = self._detect_pdf_content(final_url, content_type)
                    
                    if is_pdf:
                        logger.info("FetchDependency: Detected PDF content, attempting binary download")
                        # Step 3a: Download PDF binary content directly
                        result = await self._fetch_pdf_binary(final_url, url)
                        result.fetch_duration = time.time() - fetch_started
                        return result
                    else:
                        logger.info("FetchDependency: Detected HTML content, parsing as article")
                        # Step 3b: Get HTML content and parse as article
                        html = await page.content()
                        title = await page.title()
                        
                        # Parse with newspaper3k for clean text
                        fetch_result = FetchResult(
                            url=url,
                            content=html,
                            title=title,
                            content_type=content_type,
                            status_code=status_code,
                            final_url=final_url
                        )
                        
                        article_result = self.parse_with_newspaper3k(fetch_result)
                        
                        result = SmartFetchResult(
                            url=url,
                            final_url=final_url,
                            content_type="html_article",
                            detected_format="html",
                            clean_text=article_result.text if article_result.text else None,
                            title=article_result.title or title,
                            raw_content=html,
                            binary_content=None,
                            status_code=status_code,
                            extraction_successful=bool(article_result.text and len(article_result.text.strip()) > 100),
                            extraction_method="newspaper3k",
                            article_data=article_result,
                            fetch_duration=time.time() - fetch_started
                        )
                        
                        if result.extraction_successful:
                            logger.info(f"FetchDependency: Successfully extracted {len(result.clean_text)} chars as article")
                        else:
                            logger.warning("FetchDependency: Article extraction yielded minimal content")
                            
                        return result
                        
                finally:
                    await page.close()
                    
        except Exception as e:
            logger.error(f"FetchDependency: Smart fetch failed for {url}: {e}")
            return SmartFetchResult(
                url=url,
                content_type="unknown",
                detected_format="error",
                error=str(e),
                fetch_duration=time.time() - fetch_started
            )
    
    def _detect_pdf_content(self, final_url: str, content_type: str) -> bool:
        """
        Detect if the content is likely a PDF based on URL and content type.
        
        Args:
            final_url: Final URL after redirects
            content_type: Content-Type header value
            
        Returns:
            True if likely PDF, False otherwise
        """
        # Check content type header
        if "application/pdf" in content_type:
            return True
            
        # Check URL patterns for common PDF indicators
        pdf_indicators = [".pdf", "pdf=render", "format=pdf", "download=pdf"]
        final_url_lower = final_url.lower()
        
        for indicator in pdf_indicators:
            if indicator in final_url_lower:
                return True
                
        return False
    
    async def _fetch_pdf_binary(self, final_url: str, original_url: str) -> "SmartFetchResult":
        """
        Fetch PDF content as binary using direct HTTP request, with Camoufox fallback.
        
        Args:
            final_url: Final URL to download from
            original_url: Original URL for reference
            
        Returns:
            SmartFetchResult with binary PDF content
        """
        # First try direct HTTP download
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(final_url)
                response.raise_for_status()
                
                content = response.content
                content_type = response.headers.get("content-type", "")
                
                # Verify this is actually PDF binary
                is_pdf_binary = content.startswith(b'%PDF') if content else False
                
                if is_pdf_binary:
                    logger.info(f"FetchDependency: Successfully downloaded {len(content)} bytes of PDF via HTTP")
                    return SmartFetchResult(
                        url=original_url,
                        final_url=final_url,
                        content_type="application/pdf",
                        detected_format="pdf",
                        binary_content=content,
                        raw_content=None,
                        clean_text=None,  # Will be extracted by DocumentDependency
                        status_code=response.status_code,
                        extraction_successful=True,
                        extraction_method="http_download"
                    )
                else:
                    # Not actually PDF binary, treat as HTML
                    logger.warning("FetchDependency: Expected PDF but got non-PDF content via HTTP")
                    html_content = content.decode('utf-8', errors='ignore') if content else ""
                    
                    return SmartFetchResult(
                        url=original_url,
                        final_url=final_url,
                        content_type="text/html",
                        detected_format="html",
                        raw_content=html_content,
                        binary_content=None,
                        clean_text=None,
                        status_code=response.status_code,
                        extraction_successful=False,
                        extraction_method="fallback_html",
                        error="Expected PDF but received HTML content"
                    )
                    
        except Exception as http_error:
            logger.warning(f"FetchDependency: HTTP download failed ({http_error}), trying browser download")
            
            # Fallback to browser-based download for PDFs that need sessions/cookies
            try:
                return await self._fetch_pdf_via_browser(final_url, original_url)
                
            except Exception as browser_error:
                logger.error(f"FetchDependency: Both HTTP and browser PDF download failed")
                return SmartFetchResult(
                    url=original_url,
                    final_url=final_url,
                    content_type="unknown",
                    detected_format="error",
                    error=f"PDF download failed - HTTP: {str(http_error)}, Browser: {str(browser_error)}",
                    extraction_successful=False
                )

    async def _fetch_pdf_via_browser(self, final_url: str, original_url: str) -> "SmartFetchResult":
        """
        Download PDF using Camoufox browser for files that need session/cookies.
        
        Args:
            final_url: Final URL to download from
            original_url: Original URL for reference
            
        Returns:
            SmartFetchResult with binary PDF content
        """
        logger.info(f"FetchDependency: Attempting browser-based PDF download from {final_url}")
        
        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            
            # Set up download handling
            download_path = None
            pdf_content = None
            
            # Listen for download events
            async def handle_download(download):
                nonlocal download_path, pdf_content
                download_path = f"/tmp/pdf_download_{int(time.time())}.pdf"
                await download.save_as(download_path)
                logger.info(f"FetchDependency: PDF downloaded to {download_path}")
            
            page.on('download', handle_download)
            
            try:
                # Navigate to the PDF URL
                response = await page.goto(final_url, timeout=self.timeout_ms)
                
                # 🔍 DEBUG POINT 2: Check response details
                content_type = response.headers.get("content-type", "").lower() if response else ""
                logger.info(f"🔍 Browser content-type: {content_type}")
                logger.info(f"🔍 Response status: {response.status if response else 'None'}")
                logger.info(f"🔍 Final URL: {final_url}")
                
                if "application/pdf" in content_type:
                    # Method 1: Try to get PDF content directly from response
                    try:
                        pdf_content = await response.body()
                        
                        # 🔍 DEBUG POINT 3: Check PDF content
                        logger.info(f"🔍 PDF content type: {type(pdf_content)}")
                        logger.info(f"🔍 PDF content length: {len(pdf_content) if pdf_content else 'None'}")
                        logger.info(f"🔍 Starts with PDF: {pdf_content.startswith(b'%PDF') if pdf_content else 'False'}")
                        if pdf_content:
                            logger.info(f"🔍 First 100 bytes: {pdf_content[:100]}")
                        
                        if pdf_content and pdf_content.startswith(b'%PDF'):
                            logger.info(f"FetchDependency: Successfully got PDF via response.body() - {len(pdf_content)} bytes")
                            return SmartFetchResult(
                                url=original_url,
                                final_url=final_url,
                                content_type="application/pdf",
                                detected_format="pdf",
                                binary_content=pdf_content,
                                raw_content=None,
                                clean_text=None,
                                status_code=response.status if response else None,
                                extraction_successful=True,
                                extraction_method="browser_response_body"
                            )
                    except Exception as e:
                        logger.warning(f"FetchDependency: response.body() failed: {e}")
                    
                    # Method 2: Try triggering download if response.body() failed
                    try:
                        # Wait for potential download
                        await page.wait_for_timeout(3000)
                        
                        if download_path and os.path.exists(download_path):
                            with open(download_path, 'rb') as f:
                                pdf_content = f.read()
                            os.unlink(download_path)  # Clean up
                            
                            if pdf_content and pdf_content.startswith(b'%PDF'):
                                logger.info(f"FetchDependency: Successfully downloaded PDF via browser download - {len(pdf_content)} bytes")
                                return SmartFetchResult(
                                    url=original_url,
                                    final_url=final_url,
                                    content_type="application/pdf",
                                    detected_format="pdf",
                                    binary_content=pdf_content,
                                    raw_content=None,
                                    clean_text=None,
                                    status_code=response.status if response else None,
                                    extraction_successful=True,
                                    extraction_method="browser_download"
                                )
                    except Exception as e:
                        logger.warning(f"FetchDependency: Browser download failed: {e}")
                    
                    # Method 3: Try accessing PDF viewer content via JS
                    try:
                        # Check if this is a PDF viewer page with embedded content
                        pdf_data = await page.evaluate("""
                            () => {
                                // Try to find PDF data in various places
                                const pdfObject = document.querySelector('object[data*=".pdf"], embed[src*=".pdf"]');
                                if (pdfObject) {
                                    return pdfObject.data || pdfObject.src;
                                }
                                
                                // Check for PDF.js viewer
                                if (window.PDFViewerApplication && window.PDFViewerApplication.pdfDocument) {
                                    return 'pdf_viewer_detected';
                                }
                                
                                return null;
                            }
                        """)
                        
                        if pdf_data:
                            logger.info(f"FetchDependency: Detected PDF viewer content: {pdf_data}")
                            # This would need more work to extract actual PDF bytes
                            
                    except Exception as e:
                        logger.warning(f"FetchDependency: JS PDF extraction failed: {e}")
                    
                    logger.warning("FetchDependency: All browser PDF extraction methods failed")
                    return SmartFetchResult(
                        url=original_url,
                        final_url=final_url,
                        content_type="unknown",
                        detected_format="error",
                        error="Browser could not extract PDF content - all methods failed",
                        extraction_successful=False
                    )
                else:
                    # Not a PDF, get HTML content
                    logger.warning(f"FetchDependency: Browser response not PDF: {content_type}")
                    html_content = await page.content()
                    
                    return SmartFetchResult(
                        url=original_url,
                        final_url=final_url,
                        content_type=content_type,
                        detected_format="html",
                        raw_content=html_content,
                        binary_content=None,
                        clean_text=None,
                        status_code=response.status if response else None,
                        extraction_successful=False,
                        extraction_method="browser_fallback",
                        error="Browser returned HTML instead of PDF"
                    )
                    
            finally:
                await page.close()


@dataclass
class SmartFetchResult:
    """Result from smart content fetching with content type detection"""
    
    # URLs and routing
    url: str
    final_url: Optional[str] = None
    
    # Content detection
    content_type: str = "unknown"  # detected content type
    detected_format: str = "unknown"  # pdf, html, doc, error
    
    # Content (only one should be populated based on format)
    clean_text: Optional[str] = None  # Clean extracted text for all formats
    raw_content: Optional[str] = None  # Raw HTML content for articles
    binary_content: Optional[bytes] = None  # Binary content for PDFs/docs
    
    # Metadata
    title: Optional[str] = None
    status_code: Optional[int] = None
    
    # Processing results
    extraction_successful: bool = False
    extraction_method: Optional[str] = None  # newspaper3k, pypdf, binary_download, etc.
    error: Optional[str] = None
    
    # Performance
    fetch_duration: Optional[float] = None
    
    # Additional structured data
    article_data: Optional[Newspaper3kResult] = None  # For HTML articles
    document_metadata: Optional[Dict[str, Any]] = None  # For PDFs/docs
