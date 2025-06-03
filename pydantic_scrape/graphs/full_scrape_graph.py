"""
Complete Science Scrape Graph - following the dependency-heavy, graph-heavy pattern

This implements the full workflow from the diagram:
URL → Fetch → Detect → Science/YouTube/Article/Doc → AI Scrape → Finalize

Dependencies do all heavy lifting, nodes are pure logic gates with complex routing.

Browser-Optimized Batch Scraping - Reuses browser instances for maximum performance
Solves the browser initialization overhead by maintaining a pool of browser instances
and reusing them across multiple URLs.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union

from camoufox.async_api import AsyncCamoufox
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from pydantic_scrape.dependencies import (
    AiScraperDependency,
    ArticleDependency,
    ArticleResult,
    ContentAnalysisDependency,
    ContentAnalysisResult,
    CrossrefDependency,
    CrossrefResult,
    DocumentDependency,
    DocumentResult,
    FetchDependency,
    FetchResult,
    OpenAlexDependency,
    OpenAlexResult,
    YouTubeDependency,
    YouTubeResult,
)


# === BROWSER OPTIMIZATION CLASSES ===

@dataclass
class OptimizedBatchResult:
    """Result from browser-optimized batch scraping"""
    
    results: List[Any]
    total_processed: int
    successful_scrapes: int
    failed_scrapes: int
    total_time_seconds: float
    browser_setup_time: float
    actual_scraping_time: float
    average_time_per_url: float
    processing_errors: List[str]
    url_timing: Dict[str, float]


class BrowserPool:
    """Pool of browser instances for reuse across scraping operations"""
    
    def __init__(self, pool_size: int = 3, browser_config: Optional[Dict] = None):
        self.pool_size = pool_size
        self.browser_config = browser_config or {"headless": True, "humanize": True}
        self.browsers = []
        self.available_browsers = asyncio.Queue()
        self.setup_complete = False
    
    async def setup(self):
        """Initialize the browser pool"""
        if self.setup_complete:
            return
            
        logger.info(f"BrowserPool: Initializing {self.pool_size} browser instances")
        setup_start = time.time()
        
        # Create browsers concurrently for faster setup
        browser_tasks = [
            AsyncCamoufox(**self.browser_config).__aenter__() 
            for _ in range(self.pool_size)
        ]
        
        self.browsers = await asyncio.gather(*browser_tasks)
        
        # Add all browsers to the available queue
        for browser in self.browsers:
            await self.available_browsers.put(browser)
        
        setup_time = time.time() - setup_start
        self.setup_complete = True
        
        logger.info(f"BrowserPool: Setup complete in {setup_time:.2f}s - {len(self.browsers)} browsers ready")
        return setup_time
    
    @asynccontextmanager
    async def get_browser(self):
        """Get a browser from the pool, return it when done"""
        browser = await self.available_browsers.get()
        try:
            yield browser
        finally:
            await self.available_browsers.put(browser)
    
    async def cleanup(self):
        """Clean up all browser instances"""
        logger.info(f"BrowserPool: Cleaning up {len(self.browsers)} browsers")
        
        # Close all browsers
        cleanup_tasks = []
        for browser in self.browsers:
            try:
                cleanup_tasks.append(browser.__aexit__(None, None, None))
            except Exception as e:
                logger.warning(f"BrowserPool: Error closing browser: {e}")
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        self.browsers.clear()
        self.setup_complete = False


class BrowserAwareFetchDependency:
    """
    Modified FetchDependency that uses a provided browser instance
    instead of creating new ones.
    """
    
    def __init__(self, browser, timeout_ms: int = 30000):
        self.browser = browser
        self.timeout_ms = timeout_ms
        self.wait_for = "domcontentloaded"
    
    async def fetch_content(self, url: str, browser_config: Optional[Dict] = None):
        """Fetch content using the provided browser instance"""
        fetch_started = time.time()
        logger.info(f"BrowserAwareFetch: Fetching content from {url}")
        
        try:
            page = await self.browser.new_page()
            
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
                    content_type=response.headers.get("content-type") if response else None,
                    status_code=response.status if response else None,
                    headers=dict(response.headers) if response else {},
                    fetch_duration=time.time() - fetch_started,
                    page_load_time=page_load_time,
                    final_url=page.url,
                )
                
                logger.info(f"BrowserAwareFetch: Successfully fetched {len(html)} chars from {url}")
                return result
                
            finally:
                await page.close()
                
        except Exception as e:
            logger.error(f"BrowserAwareFetch: Error fetching {url}: {str(e)}")
            return FetchResult(
                url=url, error=str(e), fetch_duration=time.time() - fetch_started
            )
    
    async def fetch_smart_content(self, url: str, browser_config: Optional[Dict] = None, base_url: Optional[str] = None):
        """Smart content fetching using the provided browser"""
        # For now, delegate to the original smart fetch logic
        # This could be optimized further by reusing the browser
        
        # Fallback to regular fetch dependency for smart content
        # TODO: Optimize this to also use the browser pool
        regular_fetch = FetchDependency(timeout_ms=self.timeout_ms)
        return await regular_fetch.fetch_smart_content(url, browser_config, base_url)


# === MAIN SCRAPE RESULT AND STATE ===

@dataclass
class FinalScrapeResult:
    """Final structured result from complete science scraping workflow"""

    # Basic result info
    url: str
    success: bool
    content_type: str
    confidence: float

    # Processing statistics
    fetch_attempts: int
    metadata_complete: bool
    full_text_extracted: bool
    pdf_links_found: int

    # Script caching stats
    script_cache_hit: bool = False
    script_generated: bool = False
    script_worked: bool = False

    # Rich structured data (using .to_dict() results)
    content_analysis: Optional[Dict[str, Any]] = None
    openalex_data: Optional[Dict[str, Any]] = None
    crossref_data: Optional[Dict[str, Any]] = None
    youtube_data: Optional[Dict[str, Any]] = None
    article_data: Optional[Dict[str, Any]] = None
    document_data: Optional[Dict[str, Any]] = None

    # Content and links
    pdf_links: List[str] = None
    full_text_content: Optional[str] = None  # Extracted full text from PDFs
    processing_errors: List[str] = None

    # Legacy metadata field for backward compatibility
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.pdf_links is None:
            self.pdf_links = []
        if self.processing_errors is None:
            self.processing_errors = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


# State to track the entire science scraping workflow
@dataclass
class ScienceScrapeState:
    """State tracks the complete science paper extraction workflow"""

    url: str

    # Fetch results
    fetch_result: Optional[FetchResult] = None
    fetch_attempts: int = 0

    # Content detection - store full analysis result
    content_analysis: Optional[ContentAnalysisResult] = None

    # Science paper progress - store actual result objects!
    openalex_result: Optional[OpenAlexResult] = None
    crossref_result: Optional[CrossrefResult] = None
    youtube_result: Optional[YouTubeResult] = None
    article_result: Optional[ArticleResult] = None
    document_result: Optional[DocumentResult] = None
    pdf_links: List[str] = None
    full_text_extracted: bool = False
    metadata_complete: bool = False
    science_apis_processed: bool = False  # Track if we've done API lookups

    # Script caching for PDF extraction
    script_cache_hit: bool = False
    script_generated: bool = False
    script_worked: bool = False
    
    # Loop prevention
    science_node_visits: int = 0
    max_science_visits: int = 3  # Prevent infinite loops
    failed_pdf_urls: List[str] = None  # Track failed PDF downloads to avoid retries

    # Final results - initialize early and update directly
    processing_errors: List[str] = None
    final_result: FinalScrapeResult = None  # Clean structured result - initialize early

    def __post_init__(self):
        if self.pdf_links is None:
            self.pdf_links = []
        if self.processing_errors is None:
            self.processing_errors = []
        if self.failed_pdf_urls is None:
            self.failed_pdf_urls = []

        # Initialize FinalScrapeResult early to update throughout process
        if self.final_result is None:
            self.final_result = FinalScrapeResult(
                url=self.url,
                success=False,  # Will update as we progress
                content_type="unknown",
                confidence=0.0,
                fetch_attempts=0,
                metadata_complete=False,
                full_text_extracted=False,
                pdf_links_found=0,
                processing_errors=[],
            )


# Dependencies for the complete workflow
@dataclass
class CompleteScienceDeps:
    """All dependencies for complete science scraping workflow"""

    fetch: FetchDependency
    content_analysis: ContentAnalysisDependency
    ai_scraper: AiScraperDependency
    openalex: OpenAlexDependency
    crossref: CrossrefDependency
    youtube: YouTubeDependency
    article: ArticleDependency
    document: DocumentDependency


# === GRAPH NODES (Logic Gates) ===


@dataclass
class FetchNode(
    BaseNode[ScienceScrapeState, CompleteScienceDeps, Union["DetectNode", End]]
):
    """Logic gate: Fetch content, route to detection or fail"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> Union["DetectNode", End]:
        ctx.state.fetch_attempts += 1
        ctx.state.final_result.fetch_attempts = ctx.state.fetch_attempts

        # Dependency does the heavy lifting
        result = await ctx.deps.fetch.fetch_content(
            ctx.state.url, browser_config={"headless": True, "humanize": True}
        )

        # Logic gate: success or failure
        if result.error:
            ctx.state.processing_errors.append(f"Fetch failed: {result.error}")
            ctx.state.final_result.processing_errors = (
                ctx.state.processing_errors.copy()
            )
            return End(ctx.state.final_result)

        ctx.state.fetch_result = result
        return DetectNode()


@dataclass
class DetectNode(
    BaseNode[
        ScienceScrapeState,
        CompleteScienceDeps,
        Union["ScienceNode", "YouTubeNode", "ArticleNode", "DocNode"],
    ]
):
    """Logic gate: Route based on content type detection"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> Union["ScienceNode", "YouTubeNode", "ArticleNode", "DocNode"]:
        # Dependency does content analysis
        analysis = await ctx.deps.content_analysis.analyze_content(
            ctx.state.fetch_result
        )

        # Store full analysis result - includes doi, arxiv_id, pubmed_id!
        ctx.state.content_analysis = analysis

        # Update final_result with initial detection results
        ctx.state.final_result.content_type = analysis.content_type
        ctx.state.final_result.confidence = analysis.confidence
        ctx.state.final_result.content_analysis = analysis.to_dict()

        # Logic gate: route based on detected type
        if analysis.content_type == "science" and analysis.confidence > 0.7:
            return ScienceNode()
        elif "youtube" in ctx.state.url.lower():
            return YouTubeNode()
        elif analysis.content_type in ["article", "news"]:
            return ArticleNode()
        else:
            return DocNode()


@dataclass
class ScienceNode(
    BaseNode[
        ScienceScrapeState, CompleteScienceDeps, Union["AiScrapeNode", "FinalizeNode"]
    ]
):
    """Logic gate: Try to get everything needed from science APIs, route based on success"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> Union["AiScrapeNode", "FinalizeNode"]:
        # Increment visit counter to prevent infinite loops
        ctx.state.science_node_visits += 1
        
        # Prevent infinite loops between ScienceNode and AiScrapeNode
        if ctx.state.science_node_visits > ctx.state.max_science_visits:
            logger.warning(
                f"ScienceNode: Reached maximum visits ({ctx.state.max_science_visits}), forcing finalization to prevent infinite loop"
            )
            ctx.state.processing_errors.append(
                f"Forced finalization after {ctx.state.science_node_visits} ScienceNode visits to prevent infinite loop"
            )
            return FinalizeNode()
        
        # Get common data needed in both branches
        analysis = ctx.state.content_analysis
        title = ctx.state.fetch_result.title or ""

        # Check if we're returning from AiScrapeNode with new PDF links
        if ctx.state.science_apis_processed and ctx.state.pdf_links:
            logger.info(
                f"ScienceNode: Returning from AiScrapeNode with PDF links - proceeding to download (visit {ctx.state.science_node_visits})"
            )
            # Skip API lookups, go straight to PDF processing
            pdf_found = True
        else:
            # First time through - do API lookups
            logger.info("ScienceNode: First pass - performing API lookups")

            # Extract identifiers for better lookup accuracy
            doi = analysis.doi if analysis else None
            # TODO these should be added to the extensive lookups on the deps too
            arxiv_id = analysis.arxiv_id if analysis else None
            pubmed_id = analysis.pubmed_id if analysis else None

            # Dependencies do the API lookups using DOI first (much more accurate!)
            ctx.state.openalex_result = await ctx.deps.openalex.lookup(
                doi=doi, title=title
            )
            ctx.state.crossref_result = await ctx.deps.crossref.lookup(
                doi=doi, title=title
            )
            ctx.state.science_apis_processed = True  # Mark as processed

        # Check if we got PDF links (from APIs or AI scraping) and download them for full text
        pdf_found = False

        # Add any OpenAlex PDF URLs to our collection
        if ctx.state.openalex_result and ctx.state.openalex_result.pdf_urls:
            ctx.state.pdf_links.extend(ctx.state.openalex_result.pdf_urls)

        # Try smart content fetching from available PDF/full-text links
        if ctx.state.pdf_links:
            # Filter out already failed URLs
            available_urls = [url for url in ctx.state.pdf_links if url not in ctx.state.failed_pdf_urls]
            
            if not available_urls:
                logger.warning("ScienceNode: All PDF URLs have been tried and failed, routing to AiScrapeNode")
                return AiScrapeNode()
                
            for pdf_url in available_urls[:2]:  # Try first 2 available links
                try:
                    logger.info(f"ScienceNode: Smart fetching content from: {pdf_url}")
                    smart_result = await ctx.deps.fetch.fetch_smart_content(pdf_url, base_url=ctx.state.url)

                    # 🔍 DEBUG POINT 1: Check what smart fetch returned
                    logger.info(
                        f"🔍 Smart result format: {smart_result.detected_format}"
                    )
                    logger.info(
                        f"🔍 Has binary content: {smart_result.binary_content is not None}"
                    )
                    if smart_result.binary_content:
                        logger.info(
                            f"🔍 Binary content length: {len(smart_result.binary_content)}"
                        )
                        logger.info(
                            f"🔍 First 50 bytes: {smart_result.binary_content[:50]}"
                        )
                    if smart_result.clean_text:
                        logger.info(
                            f"🔍 Clean text length: {len(smart_result.clean_text)}"
                        )
                        logger.info(
                            f"🔍 Clean text start: {smart_result.clean_text[:100]}..."
                        )
                    if smart_result.raw_content:
                        logger.info(
                            f"🔍 Raw content length: {len(smart_result.raw_content)}"
                        )
                        logger.info(
                            f"🔍 Raw content start: {smart_result.raw_content[:100]}..."
                        )
                    logger.info(
                        f"🔍 Extraction method: {smart_result.extraction_method}"
                    )
                    logger.info(f"🔍 Error: {smart_result.error}")

                    if not smart_result.error:
                        if (
                            smart_result.detected_format == "pdf"
                            and smart_result.binary_content
                        ):
                            # Got binary PDF, extract text using document dependency
                            logger.info("ScienceNode: Processing binary PDF content")

                            # Extract text directly from binary content using DocumentDependency
                            pdf_doc_result = ctx.deps.document._extract_pdf_text(
                                smart_result.binary_content
                            )

                            if (
                                pdf_doc_result.extraction_successful
                                and pdf_doc_result.text
                            ):
                                # Update FinalScrapeResult directly with PDF text
                                ctx.state.final_result.full_text_content = (
                                    pdf_doc_result.text
                                )
                                ctx.state.final_result.full_text_extracted = True
                                pdf_found = True
                                logger.info(
                                    f"ScienceNode: Successfully extracted {len(pdf_doc_result.text)} characters from PDF"
                                )
                                break  # Got clean PDF text, stop trying more links
                            else:
                                logger.warning(
                                    f"ScienceNode: PDF text extraction failed: {pdf_doc_result.error}"
                                )

                        elif (
                            smart_result.detected_format == "html"
                            and smart_result.clean_text
                        ):
                            # Got clean HTML article text
                            logger.info("ScienceNode: Processing HTML article content")
                            if (
                                len(smart_result.clean_text.strip()) > 100
                            ):  # Substantial content
                                ctx.state.final_result.full_text_content = (
                                    smart_result.clean_text
                                )
                                ctx.state.final_result.full_text_extracted = True
                                pdf_found = True
                                logger.info(
                                    f"ScienceNode: Successfully extracted {len(smart_result.clean_text)} characters from HTML article"
                                )
                                break  # Got clean article text, stop trying more links
                            else:
                                logger.warning(
                                    "ScienceNode: HTML article extraction yielded minimal content"
                                )
                        else:
                            logger.warning(
                                f"ScienceNode: Smart fetch successful but no usable content: format={smart_result.detected_format}"
                            )
                    else:
                        logger.warning(
                            f"ScienceNode: Smart fetch failed: {smart_result.error}"
                        )
                        # Track this as a failed URL to avoid retrying
                        ctx.state.failed_pdf_urls.append(pdf_url)

                except Exception as e:
                    logger.error(f"ScienceNode: Smart content processing failed: {e}")
                    ctx.state.processing_errors.append(
                        f"Smart content processing failed: {e}"
                    )
                    # Track this as a failed URL to avoid retrying
                    ctx.state.failed_pdf_urls.append(pdf_url)

            # Update PDF links count in final result
            ctx.state.final_result.pdf_links_found = len(ctx.state.pdf_links)
            ctx.state.final_result.pdf_links = ctx.state.pdf_links.copy()

        # Update FinalScrapeResult with metadata using .to_dict() methods
        ctx.state.final_result.content_type = (
            analysis.content_type if analysis else "science"
        )
        ctx.state.final_result.confidence = analysis.confidence if analysis else 0.8
        ctx.state.final_result.fetch_attempts = ctx.state.fetch_attempts
        ctx.state.final_result.metadata_complete = True

        # Store structured metadata
        ctx.state.final_result.content_analysis = (
            analysis.to_dict() if analysis else None
        )
        ctx.state.final_result.openalex_data = (
            ctx.state.openalex_result.to_dict() if ctx.state.openalex_result else None
        )
        ctx.state.final_result.crossref_data = (
            ctx.state.crossref_result.to_dict() if ctx.state.crossref_result else None
        )

        # Legacy metadata for backward compatibility
        ctx.state.final_result.metadata = {
            "title": title,
            "url": ctx.state.url,
            "openalex": ctx.state.final_result.openalex_data,
            "crossref": ctx.state.final_result.crossref_data,
            "content_analysis": ctx.state.final_result.content_analysis,
        }

        # Logic gate: got PDF or need to scrape for it?
        if pdf_found:
            ctx.state.full_text_extracted = True
            return FinalizeNode()
        else:
            # Need AI scraping to find PDF link
            return AiScrapeNode()


@dataclass
class YouTubeNode(BaseNode[ScienceScrapeState, CompleteScienceDeps, "FinalizeNode"]):
    """Logic gate: Handle YouTube content with proper metadata and subtitle extraction"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> "FinalizeNode":
        try:
            # Use YouTube dependency for rich metadata and subtitle extraction
            ctx.state.youtube_result = await ctx.deps.youtube.extract_metadata(
                ctx.state.url
            )

            if ctx.state.youtube_result.extraction_successful:
                # Update FinalScrapeResult directly with YouTube data
                ctx.state.final_result.youtube_data = ctx.state.youtube_result.to_dict()
                ctx.state.final_result.content_type = "youtube"
                ctx.state.final_result.metadata_complete = True

                # Mark as having content if we got transcript and update final_result
                if ctx.state.youtube_result.transcript:
                    ctx.state.final_result.full_text_content = (
                        ctx.state.youtube_result.transcript
                    )
                    ctx.state.final_result.full_text_extracted = True
                    logger.info(
                        f"YouTubeNode: Successfully extracted transcript with {len(ctx.state.youtube_result.transcript)} characters"
                    )

            else:
                ctx.state.processing_errors.append(
                    f"YouTube extraction failed: {ctx.state.youtube_result.error}"
                )
                ctx.state.final_result.processing_errors = (
                    ctx.state.processing_errors.copy()
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"YouTube processing failed: {e}")
            ctx.state.final_result.processing_errors = (
                ctx.state.processing_errors.copy()
            )

        return FinalizeNode()


@dataclass
class ArticleNode(BaseNode[ScienceScrapeState, CompleteScienceDeps, "FinalizeNode"]):
    """Logic gate: Handle article content with newspaper3k and goose"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> "FinalizeNode":
        try:
            # Use Article dependency for robust content extraction
            ctx.state.article_result = await ctx.deps.article.extract_article(
                ctx.state.fetch_result
            )

            if ctx.state.article_result.extraction_successful:
                # Update FinalScrapeResult directly with article data
                ctx.state.final_result.article_data = ctx.state.article_result.to_dict()
                ctx.state.final_result.content_type = "article"
                ctx.state.final_result.metadata_complete = True

                # Mark as having content if we got substantial text and update final_result
                if (
                    ctx.state.article_result.text
                    and len(ctx.state.article_result.text.strip()) > 100
                ):
                    ctx.state.final_result.full_text_content = (
                        ctx.state.article_result.text
                    )
                    ctx.state.final_result.full_text_extracted = True
                    logger.info(
                        f"ArticleNode: Successfully extracted {len(ctx.state.article_result.text)} characters"
                    )

            else:
                ctx.state.processing_errors.append(
                    f"Article extraction failed: {ctx.state.article_result.error}"
                )
                ctx.state.final_result.processing_errors = (
                    ctx.state.processing_errors.copy()
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"Article processing failed: {e}")
            ctx.state.final_result.processing_errors = (
                ctx.state.processing_errors.copy()
            )

        return FinalizeNode()


@dataclass
class DocNode(BaseNode[ScienceScrapeState, CompleteScienceDeps, "FinalizeNode"]):
    """Logic gate: Handle document files (PDF, DOCX, EPUB, etc.) with binary download and text extraction"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> "FinalizeNode":
        try:
            # Use Document dependency for robust document processing
            ctx.state.document_result = await ctx.deps.document.extract_document(
                ctx.state.fetch_result
            )

            if ctx.state.document_result.extraction_successful:
                # Update FinalScrapeResult directly with document data
                ctx.state.final_result.document_data = (
                    ctx.state.document_result.to_dict()
                )
                ctx.state.final_result.content_type = "document"
                ctx.state.final_result.metadata_complete = True

                # Mark as having content if we got substantial text and update final_result
                if (
                    ctx.state.document_result.text
                    and len(ctx.state.document_result.text.strip()) > 100
                ):
                    ctx.state.final_result.full_text_content = (
                        ctx.state.document_result.text
                    )
                    ctx.state.final_result.full_text_extracted = True
                    logger.info(
                        f"DocNode: Successfully extracted {len(ctx.state.document_result.text)} characters"
                    )

            else:
                ctx.state.processing_errors.append(
                    f"Document extraction failed: {ctx.state.document_result.error}"
                )
                ctx.state.final_result.processing_errors = (
                    ctx.state.processing_errors.copy()
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"Document processing failed: {e}")
            ctx.state.final_result.processing_errors = (
                ctx.state.processing_errors.copy()
            )

        return FinalizeNode()


@dataclass
class AiScrapeNode(
    BaseNode[
        ScienceScrapeState,
        CompleteScienceDeps,
        Union["ScienceNode", "DocNode", "FinalizeNode"],
    ]
):
    """Logic gate: AI scrape to get PDF links, route back to ScienceNode for science content"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> Union["ScienceNode", "DocNode", "FinalizeNode"]:
        # AI scrape to find PDF links
        class PdfExtraction(BaseModel):
            pdf_links: List[str] = Field(description="All PDF download links found")
            full_text_available: bool = Field(
                description="Whether full text is available"
            )

        try:
            pdf_data = await ctx.deps.ai_scraper.extract_data(
                fetch_result=ctx.state.fetch_result,
                output_type=PdfExtraction,
                extraction_prompt="Find all PDF download links and determine if full text is available",
            )

            ctx.state.pdf_links.extend(pdf_data.pdf_links)
            ctx.state.script_worked = True

            # Logic gate: found PDFs for science content? Route back to ScienceNode!
            if pdf_data.pdf_links:
                # Check if this is science content that should go back to ScienceNode
                analysis = ctx.state.content_analysis
                if (
                    analysis
                    and analysis.content_type == "science"
                    and analysis.confidence > 0.7
                ):
                    logger.info(
                        f"AiScrapeNode: Found {len(pdf_data.pdf_links)} PDF links for science content - routing back to ScienceNode"
                    )
                    return ScienceNode()
                else:
                    # Non-science content with PDFs - treat as document
                    ctx.state.full_text_extracted = True
                    return FinalizeNode()
            elif not pdf_data.full_text_available:
                # No PDFs and no full text - handle as document
                return DocNode()
            else:
                # Couldn't find PDFs but text should be available - finalize anyway
                return FinalizeNode()

        except Exception as e:
            ctx.state.processing_errors.append(f"AI PDF extraction failed: {e}")
            return DocNode()


@dataclass
class FinalizeNode(BaseNode[ScienceScrapeState, CompleteScienceDeps, End]):
    """Logic gate: Compose final result object"""

    async def run(
        self, ctx: GraphRunContext[ScienceScrapeState, CompleteScienceDeps]
    ) -> End:
        # Finalize the FinalScrapeResult we've been updating throughout the process
        logger.info("FinalizeNode: Finalizing scraped result")

        # Mark as successful and add any final updates
        ctx.state.final_result.success = True

        # Add any missing structured data from other content types
        if ctx.state.youtube_result:
            ctx.state.final_result.youtube_data = ctx.state.youtube_result.to_dict()
        if ctx.state.article_result:
            ctx.state.final_result.article_data = ctx.state.article_result.to_dict()
        if ctx.state.document_result:
            ctx.state.final_result.document_data = ctx.state.document_result.to_dict()

        # Add script caching info
        ctx.state.final_result.script_cache_hit = ctx.state.script_cache_hit
        ctx.state.final_result.script_generated = ctx.state.script_generated
        ctx.state.final_result.script_worked = ctx.state.script_worked

        # Final processing errors update
        ctx.state.final_result.processing_errors = ctx.state.processing_errors.copy()

        logger.info(
            f"FinalizeNode: Completed scraping {ctx.state.url} - "
            f"success: {ctx.state.final_result.success}, "
            f"content_type: {ctx.state.final_result.content_type}, "
            f"full_text: {ctx.state.final_result.full_text_extracted}"
        )

        # Return the FinalScrapeResult we've been building throughout the process
        return End(ctx.state.final_result)


# === GRAPH ASSEMBLY ===

# The complete science scrape graph following the diagram
complete_science_graph = Graph(
    nodes=[
        FetchNode,
        DetectNode,
        ScienceNode,
        YouTubeNode,
        ArticleNode,
        DocNode,
        AiScrapeNode,
        FinalizeNode,
    ],
)


# === BROWSER OPTIMIZATION FUNCTIONALITY ===

class BrowserOptimizedScraping:
    """
    High-performance batch scraping with browser instance reuse.
    
    Key optimizations:
    1. Browser pool to eliminate startup overhead
    2. Concurrent scraping with shared browser instances  
    3. Efficient resource management
    """
    
    def __init__(
        self, 
        max_concurrent: int = 3,
        browser_pool_size: Optional[int] = None,
        timeout_per_url: float = 60.0,
        browser_config: Optional[Dict] = None
    ):
        """
        Initialize browser-optimized scraping.
        
        Args:
            max_concurrent: Maximum concurrent scraping operations
            browser_pool_size: Size of browser pool (defaults to max_concurrent)
            timeout_per_url: Timeout per URL operation
            browser_config: Browser configuration for Camoufox
        """
        self.max_concurrent = max_concurrent
        self.browser_pool_size = browser_pool_size or max_concurrent
        self.timeout_per_url = timeout_per_url
        self.browser_config = browser_config or {"headless": True, "humanize": True}
        
        logger.info(f"BrowserOptimized: Configured for {max_concurrent} concurrent, {self.browser_pool_size} browser pool")

    async def scrape_urls_with_browser_pool(
        self, 
        urls: List[str],
        custom_scrape_function: Optional[callable] = None
    ) -> OptimizedBatchResult:
        """
        Scrape URLs using a shared browser pool for maximum performance.
        
        Args:
            urls: List of URLs to scrape
            custom_scrape_function: Optional custom scraping function (uses full_scrape_graph by default)
            
        Returns:
            OptimizedBatchResult with performance metrics
        """
        total_start = time.time()
        
        # Set up browser pool
        browser_pool = BrowserPool(self.browser_pool_size, self.browser_config)
        browser_setup_time = await browser_pool.setup()
        
        scraping_start = time.time()
        
        try:
            # Determine scraping function
            if custom_scrape_function:
                scrape_func = custom_scrape_function
            else:
                scrape_func = self._default_scrape_with_browser_pool
            
            # Execute concurrent scraping with browser pool
            results = await self._scrape_concurrent_with_pool(
                urls, browser_pool, scrape_func
            )
            
        finally:
            # Always clean up browser pool
            await browser_pool.cleanup()
        
        scraping_time = time.time() - scraping_start
        total_time = time.time() - total_start
        
        # Analyze results
        successful_results = []
        failed_results = []
        processing_errors = []
        url_timing = {}
        
        for result_data in results:
            if isinstance(result_data, dict) and 'url' in result_data:
                url = result_data['url']
                timing = result_data.get('timing', 0)
                result = result_data.get('result')
                error = result_data.get('error')
                
                url_timing[url] = timing
                
                if error:
                    processing_errors.append(f"{url}: {error}")
                    failed_results.append(self._create_error_result(url, error))
                else:
                    successful_results.append(result)
        
        avg_time = (total_time / len(urls)) if urls else 0
        
        logger.info(f"BrowserOptimized: 🏁 Total: {total_time:.2f}s (setup: {browser_setup_time:.2f}s, scraping: {scraping_time:.2f}s)")
        logger.info(f"BrowserOptimized: ✅ Success: {len(successful_results)}/{len(urls)}")
        
        return OptimizedBatchResult(
            results=successful_results + failed_results,
            total_processed=len(urls),
            successful_scrapes=len(successful_results),
            failed_scrapes=len(failed_results),
            total_time_seconds=total_time,
            browser_setup_time=browser_setup_time,
            actual_scraping_time=scraping_time,
            average_time_per_url=avg_time,
            processing_errors=processing_errors,
            url_timing=url_timing
        )

    async def _scrape_concurrent_with_pool(
        self, 
        urls: List[str], 
        browser_pool: BrowserPool, 
        scrape_func: callable
    ) -> List[Dict]:
        """Execute concurrent scraping using the browser pool"""
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_single_with_pool(url: str):
            async with semaphore:
                url_start = time.time()
                
                try:
                    logger.info(f"BrowserOptimized: Processing {url}")
                    
                    # Get browser from pool and scrape
                    async with browser_pool.get_browser() as browser:
                        result = await asyncio.wait_for(
                            scrape_func(url, browser),
                            timeout=self.timeout_per_url
                        )
                    
                    url_time = time.time() - url_start
                    logger.info(f"BrowserOptimized: ✅ Completed {url} in {url_time:.2f}s")
                    
                    return {
                        'url': url,
                        'result': result,
                        'timing': url_time,
                        'error': None
                    }
                    
                except Exception as e:
                    url_time = time.time() - url_start
                    logger.error(f"BrowserOptimized: ❌ {url} failed: {e}")
                    
                    return {
                        'url': url,
                        'result': None,
                        'timing': url_time,
                        'error': str(e)
                    }
        
        # Execute all scraping tasks
        logger.info(f"BrowserOptimized: Starting {len(urls)} concurrent tasks")
        tasks = [scrape_single_with_pool(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _default_scrape_with_browser_pool(self, url: str, browser) -> Any:
        """
        Default scraping function that uses the browser pool efficiently.
        
        This recreates the essential parts of execute_full_scrape_graph but with
        a provided browser instance instead of creating new ones.
        """
        # Create a browser-aware fetch dependency
        fetch_dep = BrowserAwareFetchDependency(browser, timeout_ms=30000)
        
        # Create other dependencies normally
        deps = CompleteScienceDeps(
            fetch=fetch_dep,
            content_analysis=ContentAnalysisDependency(),
            ai_scraper=AiScraperDependency(),
            openalex=OpenAlexDependency(fuzzy_match_threshold=85.0),
            crossref=CrossrefDependency(),
            youtube=YouTubeDependency(extract_subtitles=True, subtitle_lang="en"),
            article=ArticleDependency(prefer_newspaper=True, language="en"),
            document=DocumentDependency(save_binary=True, save_temp_file=False),
        )
        
        # Initial state
        initial_state = ScienceScrapeState(url=url)
        
        # Run the graph with browser-aware dependencies
        result = await complete_science_graph.run(
            FetchNode(),
            state=initial_state,
            deps=deps,
        )
        
        return result.output

    def _create_error_result(self, url: str, error_message: str):
        """Create standardized error result"""
        return FinalScrapeResult(
            url=url,
            success=False,
            content_type="error",
            confidence=0.0,
            fetch_attempts=0,
            metadata_complete=False,
            full_text_extracted=False,
            pdf_links_found=0,
            processing_errors=[error_message]
        )


async def execute_batch_scrape_graph(
    urls: List[str], 
    max_concurrent: int = 3,
    browser_pool_size: Optional[int] = None,
    timeout_per_url: float = 60.0,
    browser_config: Optional[Dict] = None
) -> OptimizedBatchResult:
    """
    Execute high-performance batch scraping using browser pooling for maximum efficiency.
    
    This function provides significant performance improvements over individual scraping by:
    - Reusing browser instances across multiple URLs
    - Concurrent processing with controlled resource usage
    - Optimized browser initialization overhead
    
    Examples:
        Basic batch scraping:
        ```python
        urls = [
            "https://arxiv.org/abs/2301.00001",
            "https://example.com/paper.pdf",
            "https://youtube.com/watch?v=xyz123"
        ]
        result = await execute_batch_scrape_graph(urls, max_concurrent=5)
        
        print(f"Processed {result.total_processed} URLs in {result.total_time_seconds:.2f}s")
        print(f"Success rate: {result.successful_scrapes}/{result.total_processed}")
        
        for scrape_result in result.results:
            if scrape_result.success:
                print(f"✅ {scrape_result.url}: {scrape_result.content_type}")
            else:
                print(f"❌ {scrape_result.url}: {scrape_result.processing_errors}")
        ```
        
        With custom configuration:
        ```python
        result = await execute_batch_scrape_graph(
            urls,
            max_concurrent=10,
            browser_pool_size=5,
            timeout_per_url=120.0,
            browser_config={"headless": False, "humanize": True}
        )
        ```
    
    Args:
        urls: List of URLs to scrape
        max_concurrent: Maximum concurrent scraping operations (default: 3)
        browser_pool_size: Size of browser pool (defaults to max_concurrent)
        timeout_per_url: Timeout per URL in seconds (default: 60.0)
        browser_config: Browser configuration for Camoufox
            - headless (bool): Run browser in headless mode (default: True)
            - humanize (bool): Use human-like behavior (default: True)
    
    Returns:
        OptimizedBatchResult containing:
            - results (List[FinalScrapeResult]): Individual scrape results
            - total_processed (int): Total number of URLs processed
            - successful_scrapes (int): Number of successful scrapes
            - failed_scrapes (int): Number of failed scrapes
            - total_time_seconds (float): Total execution time
            - browser_setup_time (float): Time spent setting up browser pool
            - actual_scraping_time (float): Time spent on actual scraping
            - average_time_per_url (float): Average processing time per URL
            - processing_errors (List[str]): Any errors encountered
            - url_timing (Dict[str, float]): Per-URL timing information
    
    Raises:
        Exception: If browser pool setup fails or critical errors occur
        
    Note:
        Requires OPENAI_API_KEY environment variable for AI-powered fallbacks.
        Browser pool size should be balanced with system resources.
    """
    
    scraper = BrowserOptimizedScraping(
        max_concurrent=max_concurrent,
        browser_pool_size=browser_pool_size,
        timeout_per_url=timeout_per_url,
        browser_config=browser_config
    )
    
    logger.info(f"🚀 Starting batch scrape for {len(urls)} URLs")
    result = await scraper.scrape_urls_with_browser_pool(urls)
    
    logger.info(f"✅ Batch scraping completed!")
    logger.info(f"⏱️  Total time: {result.total_time_seconds:.2f}s")
    logger.info(f"🔧 Browser setup: {result.browser_setup_time:.2f}s")
    logger.info(f"⚡ Actual scraping: {result.actual_scraping_time:.2f}s")
    logger.info(f"📈 Average per URL: {result.average_time_per_url:.2f}s")
    logger.info(f"✅ Success rate: {result.successful_scrapes}/{result.total_processed}")
    
    return result


async def execute_full_scrape_graph(
    url: str, browser_config: Optional[Dict] = None
) -> FinalScrapeResult:
    """
    Extract full-text content and metadata from scientific papers, articles, and documents.

    This function automatically detects content type and uses the best extraction method:
    - **Scientific papers**: OpenAlex + Crossref metadata, PDF text extraction
    - **Articles/News**: Clean text via newspaper3k
    - **YouTube videos**: Transcript extraction
    - **Documents**: PDF/DOCX/EPUB text extraction
    - **Protected content**: Browser automation for paywalled/protected content

    Examples:
        Basic usage:
        ```python
        result = await execute_full_scrape_graph("https://arxiv.org/abs/2301.00001")
        print(result.full_text_content)  # Extracted text
        print(result.openalex_data)      # Academic metadata
        ```

        With custom browser config:
        ```python
        result = await execute_full_scrape_graph(
            "https://example.com/paper.pdf",
            browser_config={"headless": False, "humanize": True}
        )
        ```

    Args:
        url: URL to scrape (scientific papers, articles, PDFs, YouTube videos)
        browser_config: Optional browser configuration for Camoufox
            - headless (bool): Run browser in headless mode (default: True)
            - humanize (bool): Use human-like behavior (default: True)

    Returns:
        FinalScrapeResult containing:
            - full_text_content (str): Extracted clean text content
            - content_type (str): Detected content type (science/article/youtube/document)
            - openalex_data (dict): Academic metadata from OpenAlex
            - crossref_data (dict): Reference data from Crossref
            - pdf_links (list): Found PDF download URLs
            - success (bool): Whether extraction succeeded
            - processing_errors (list): Any errors encountered during processing

    Raises:
        Exception: If the URL is invalid or network errors occur

    Note:
        Requires OPENAI_API_KEY environment variable for AI-powered fallbacks.
        Some protected content may require institutional access.
    """

    # Dependencies do ALL the heavy lifting
    deps = CompleteScienceDeps(
        fetch=FetchDependency(timeout_ms=30000),
        content_analysis=ContentAnalysisDependency(),
        ai_scraper=AiScraperDependency(),
        openalex=OpenAlexDependency(fuzzy_match_threshold=85.0),
        crossref=CrossrefDependency(),
        youtube=YouTubeDependency(extract_subtitles=True, subtitle_lang="en"),
        article=ArticleDependency(prefer_newspaper=True, language="en"),
        document=DocumentDependency(save_binary=True, save_temp_file=False),
    )

    # Initial state
    initial_state = ScienceScrapeState(url=url)

    # Run the graph - nodes are pure logic gates, dependencies do the work
    result = await complete_science_graph.run(
        FetchNode(),  # Starting node
        state=initial_state,
        deps=deps,
    )

    return result.output


# Export the complete workflow
__all__ = [
    "complete_science_graph",
    "execute_full_scrape_graph",
    "execute_batch_scrape_graph",
    "OptimizedBatchResult",
    "BrowserOptimizedScraping",
    "BrowserPool",
    "ScienceScrapeState",
    "CompleteScienceDeps",
    "FinalScrapeResult",
]
