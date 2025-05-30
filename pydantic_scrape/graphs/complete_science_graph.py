"""
Complete Science Scrape Graph - following the dependency-heavy, graph-heavy pattern

This implements the full workflow from the diagram:
URL → Fetch → Detect → Science/YouTube/Article/Doc → AI Scrape → Finalize

Dependencies do all heavy lifting, nodes are pure logic gates with complex routing.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union

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

    # Final results
    paper_metadata: Optional[Dict] = None  # Legacy - keep for compatibility
    final_content: Optional[str] = None
    processing_errors: List[str] = None
    final_result: Optional[FinalScrapeResult] = None  # Clean structured result

    def __post_init__(self):
        if self.pdf_links is None:
            self.pdf_links = []
        if self.processing_errors is None:
            self.processing_errors = []


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

        # Dependency does the heavy lifting
        result = await ctx.deps.fetch.fetch_content(
            ctx.state.url, browser_config={"headless": True, "humanize": True}
        )

        # Logic gate: success or failure
        if result.error:
            ctx.state.processing_errors.append(f"Fetch failed: {result.error}")
            return End({"error": "fetch_failed", "details": result.error})

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
        # Get common data needed in both branches
        analysis = ctx.state.content_analysis
        title = ctx.state.fetch_result.title or ""
        
        # Check if we're returning from AiScrapeNode with new PDF links
        if ctx.state.science_apis_processed and ctx.state.pdf_links:
            logger.info("ScienceNode: Returning from AiScrapeNode with PDF links - proceeding to download")
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
            ctx.state.openalex_result = await ctx.deps.openalex.lookup(doi=doi, title=title)
            ctx.state.crossref_result = await ctx.deps.crossref.lookup(doi=doi, title=title)
            ctx.state.science_apis_processed = True  # Mark as processed

        # Check if we got PDF links (from APIs or AI scraping) and download them for full text
        pdf_found = False
        
        # Add any OpenAlex PDF URLs to our collection
        if ctx.state.openalex_result and ctx.state.openalex_result.pdf_urls:
            ctx.state.pdf_links.extend(ctx.state.openalex_result.pdf_urls)

        # Try to download and extract full text from available PDFs
        if ctx.state.pdf_links:
            for pdf_url in ctx.state.pdf_links[:2]:  # Try first 2 PDFs
                try:
                    logger.info(f"ScienceNode: Attempting to download PDF: {pdf_url}")
                    pdf_fetch_result = await ctx.deps.fetch.fetch_content(pdf_url)

                    if not pdf_fetch_result.error:
                        # Use document dependency to extract text from PDF
                        pdf_doc_result = await ctx.deps.document.extract_document(
                            pdf_fetch_result
                        )

                        if pdf_doc_result.extraction_successful and pdf_doc_result.text:
                            ctx.state.final_content = pdf_doc_result.text
                            pdf_found = True
                            logger.info(
                                f"ScienceNode: Successfully extracted {len(pdf_doc_result.text)} characters from PDF"
                            )
                            break  # Got full text, stop trying more PDFs
                        else:
                            logger.warning(
                                f"ScienceNode: PDF text extraction failed: {pdf_doc_result.error}"
                            )
                    else:
                        logger.warning(
                            f"ScienceNode: PDF download failed: {pdf_fetch_result.error}"
                        )

                except Exception as e:
                    logger.error(f"ScienceNode: PDF processing failed: {e}")
                    ctx.state.processing_errors.append(f"PDF processing failed: {e}")

            # Mark as found if we got any PDF links (even if extraction failed)
            if ctx.state.pdf_links:
                pdf_found = True

        # Simple metadata composition using .to_dict() methods - much cleaner!
        ctx.state.paper_metadata = {
            "title": title,
            "url": ctx.state.url,
            "openalex": ctx.state.openalex_result.to_dict()
            if ctx.state.openalex_result
            else None,
            "crossref": ctx.state.crossref_result.to_dict()
            if ctx.state.crossref_result
            else None,
            "content_analysis": analysis.to_dict() if analysis else None,
        }
        ctx.state.metadata_complete = True

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
                # Store rich YouTube metadata using .to_dict()
                ctx.state.paper_metadata = {
                    "type": "youtube",
                    "url": ctx.state.url,
                    "youtube": ctx.state.youtube_result.to_dict(),
                }
                ctx.state.metadata_complete = True

                # Mark as having content if we got transcript
                if ctx.state.youtube_result.transcript:
                    ctx.state.full_text_extracted = True

            else:
                ctx.state.processing_errors.append(
                    f"YouTube extraction failed: {ctx.state.youtube_result.error}"
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"YouTube processing failed: {e}")

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
                # Store rich article metadata using .to_dict()
                ctx.state.paper_metadata = {
                    "type": "article",
                    "url": ctx.state.url,
                    "article": ctx.state.article_result.to_dict(),
                }
                ctx.state.metadata_complete = True

                # Mark as having content if we got substantial text
                if (
                    ctx.state.article_result.text
                    and len(ctx.state.article_result.text.strip()) > 100
                ):
                    ctx.state.full_text_extracted = True

            else:
                ctx.state.processing_errors.append(
                    f"Article extraction failed: {ctx.state.article_result.error}"
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"Article processing failed: {e}")

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
                # Store rich document metadata using .to_dict()
                ctx.state.paper_metadata = {
                    "type": "document",
                    "url": ctx.state.url,
                    "document": ctx.state.document_result.to_dict(),
                }
                ctx.state.metadata_complete = True

                # Mark as having content if we got substantial text
                if (
                    ctx.state.document_result.text
                    and len(ctx.state.document_result.text.strip()) > 100
                ):
                    ctx.state.full_text_extracted = True

            else:
                ctx.state.processing_errors.append(
                    f"Document extraction failed: {ctx.state.document_result.error}"
                )

        except Exception as e:
            ctx.state.processing_errors.append(f"Document processing failed: {e}")

        return FinalizeNode()


@dataclass
class AiScrapeNode(
    BaseNode[ScienceScrapeState, CompleteScienceDeps, Union["ScienceNode", "DocNode", "FinalizeNode"]]
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
                if analysis and analysis.content_type == "science" and analysis.confidence > 0.7:
                    logger.info(f"AiScrapeNode: Found {len(pdf_data.pdf_links)} PDF links for science content - routing back to ScienceNode")
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
        # Create clean structured result using FinalScrapeResult dataclass
        analysis = ctx.state.content_analysis

        # Determine if we actually got full text
        has_full_text = ctx.state.full_text_extracted or (
            ctx.state.final_content and len(ctx.state.final_content.strip()) > 100
        )

        # Create final structured result
        ctx.state.final_result = FinalScrapeResult(
            # Basic info
            url=ctx.state.url,
            success=True,
            content_type=analysis.content_type if analysis else "unknown",
            confidence=analysis.confidence if analysis else 0.0,
            # Processing stats
            fetch_attempts=ctx.state.fetch_attempts,
            metadata_complete=ctx.state.metadata_complete,
            full_text_extracted=has_full_text,
            pdf_links_found=len(ctx.state.pdf_links),
            # Script caching
            script_cache_hit=ctx.state.script_cache_hit,
            script_generated=ctx.state.script_generated,
            script_worked=ctx.state.script_worked,
            # Rich structured data using .to_dict() results
            content_analysis=analysis.to_dict() if analysis else None,
            openalex_data=ctx.state.openalex_result.to_dict()
            if ctx.state.openalex_result
            else None,
            crossref_data=ctx.state.crossref_result.to_dict()
            if ctx.state.crossref_result
            else None,
            youtube_data=ctx.state.youtube_result.to_dict()
            if ctx.state.youtube_result
            else None,
            article_data=ctx.state.article_result.to_dict()
            if ctx.state.article_result
            else None,
            document_data=ctx.state.document_result.to_dict()
            if ctx.state.document_result
            else None,
            # Content and errors
            pdf_links=ctx.state.pdf_links.copy(),
            full_text_content=ctx.state.final_content,
            processing_errors=ctx.state.processing_errors.copy(),
            # Legacy compatibility
            metadata=ctx.state.paper_metadata,
        )

        # Return both the clean structured result and legacy dict format
        return End(ctx.state.final_result.to_dict())


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
    ]
)


async def scrape_science_complete(
    url: str, browser_config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Complete science scraping workflow following the graph-heavy, dependency-heavy pattern.

    Implements the full flow from the diagram:
    URL → Fetch → Detect → Science/YouTube/Article/Doc → AI Scrape → Finalize

    Args:
        url: URL to scrape
        browser_config: Optional browser configuration

    Returns:
        Complete structured result with metadata, PDFs, and processing stats
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
    "scrape_science_complete",
    "ScienceScrapeState",
    "CompleteScienceDeps",
]
