"""
Google Search -> Batch Scrape -> Batch Summarize -> Answer Graph

Uses Google Custom Search Engine to find relevant URLs, then:
1. GoogleSearchNode: Find relevant URLs using Google Custom Search
2. BatchScrapeNode: Scrape all URLs efficiently with browser pooling
3. BatchSummarizeNode: Summarize all results in a single API call
4. AnswerNode: Generate final answer from batch summaries

This provides web search capabilities using Google's search engine.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

# Import batch summarization
from pydantic_scrape.agents.summarization import (
    SummarizedResult,
    summarize_content,
)
from pydantic_scrape.dependencies.google_search import GoogleCustomSearchClient

# Import the optimized batch functions
from pydantic_scrape.graphs.full_scrape_graph import (
    FinalScrapeResult,
    execute_batch_scrape_graph,
)


class FinalAnswer(BaseModel):
    """Structured final answer with sources"""

    answer: str = Field(description="Comprehensive answer to the query")
    key_points: List[str] = Field(
        description="Main points from the research", default_factory=list
    )
    sources: List[str] = Field(description="Source URLs used", default_factory=list)
    confidence: float = Field(
        description="Confidence in the answer", ge=0.0, le=1.0, default=0.8
    )

    # Processing metadata
    total_sources_found: int = Field(description="Total sources discovered", default=0)
    successful_scrapes: int = Field(
        description="Successfully scraped sources", default=0
    )
    summaries_generated: int = Field(description="Summaries created", default=0)


# State for the Google search workflow
@dataclass
class GoogleSearchScrapeState:
    """State for the complete Google search -> batch scrape -> batch summarize workflow"""

    # Input
    query: str
    max_results: int = 10
    max_scrape_urls: int = 5

    # Search phase
    search_results: List[Dict[str, Any]] = None
    relevant_urls: List[str] = None

    # Batch scraping phase
    scrape_results: List[FinalScrapeResult] = None
    successful_scrapes: int = 0
    scraping_time: float = 0

    # Batch summarization phase
    summaries: List[SummarizedResult] = None
    summarization_time: float = 0

    # Final answer
    final_answer: Optional[FinalAnswer] = None

    # Processing metadata
    processing_errors: List[str] = None
    total_processing_time: float = 0

    def __post_init__(self):
        if self.search_results is None:
            self.search_results = []
        if self.relevant_urls is None:
            self.relevant_urls = []
        if self.scrape_results is None:
            self.scrape_results = []
        if self.summaries is None:
            self.summaries = []
        if self.processing_errors is None:
            self.processing_errors = []


@dataclass
class GoogleSearchScrapeAnswerDeps:
    """Dependencies for the Google search workflow"""

    google_search_client: GoogleCustomSearchClient = None

    def __post_init__(self):
        if self.google_search_client is None:
            self.google_search_client = GoogleCustomSearchClient()


# === GOOGLE SEARCH GRAPH NODES ===


@dataclass
class GoogleSearchNode(
    BaseNode[
        GoogleSearchScrapeState,
        GoogleSearchScrapeAnswerDeps,
        Union["BatchScrapeNode", End],
    ]
):
    """Find relevant URLs using Google Custom Search"""

    async def run(
        self,
        ctx: GraphRunContext[GoogleSearchScrapeState, GoogleSearchScrapeAnswerDeps],
    ) -> Union["BatchScrapeNode", End]:
        logger.info(f"GoogleSearchNode: Starting Google search for '{ctx.state.query}'")

        try:
            # Check if Google Search is available
            if not ctx.deps.google_search_client.enabled:
                error_msg = "Google Custom Search not configured - missing API key or Search Engine ID"
                ctx.state.processing_errors.append(error_msg)
                logger.error(f"GoogleSearchNode: {error_msg}")
                return End({"error": error_msg, "query": ctx.state.query})

            # Perform Google search
            search_results = await ctx.deps.google_search_client.search(
                query=ctx.state.query, num_results=ctx.state.max_results
            )

            ctx.state.search_results = search_results
            logger.info(
                f"GoogleSearchNode: Google search completed - {len(search_results)} results"
            )

            if not search_results:
                return End(
                    {"error": "No search results found", "query": ctx.state.query}
                )

            # Extract URLs from search results (limit to max_scrape_urls)
            extracted_urls = []
            for result in search_results[: ctx.state.max_scrape_urls]:
                if "link" in result and result["link"]:
                    extracted_urls.append(result["link"])
                    logger.info(f"GoogleSearchNode: Added URL: {result['link']}")

            ctx.state.relevant_urls = extracted_urls

            logger.info(
                f"GoogleSearchNode: Found {len(ctx.state.relevant_urls)} URLs to scrape"
            )
            return BatchScrapeNode()

        except Exception as e:
            error_msg = f"Google search failed: {e}"
            ctx.state.processing_errors.append(error_msg)
            logger.error(f"GoogleSearchNode: {error_msg}")
            return End({"error": str(e), "query": ctx.state.query})


@dataclass
class BatchScrapeNode(
    BaseNode[
        GoogleSearchScrapeState,
        GoogleSearchScrapeAnswerDeps,
        Union["BatchSummarizeNode", End],
    ]
):
    """Scrape all URLs efficiently using browser pooling"""

    async def run(
        self,
        ctx: GraphRunContext[GoogleSearchScrapeState, GoogleSearchScrapeAnswerDeps],
    ) -> Union["BatchSummarizeNode", End]:
        logger.info(
            f"BatchScrapeNode: Batch scraping {len(ctx.state.relevant_urls)} URLs"
        )

        if not ctx.state.relevant_urls:
            return End({"error": "No URLs to scrape", "query": ctx.state.query})

        try:
            import time

            start_time = time.time()

            # Use optimized batch scraping with browser pooling
            batch_result = await execute_batch_scrape_graph(
                urls=ctx.state.relevant_urls,
                max_concurrent=min(3, len(ctx.state.relevant_urls)),
                timeout_per_url=90.0,
                browser_pool_size=min(3, len(ctx.state.relevant_urls)),
            )

            ctx.state.scrape_results = batch_result.results
            ctx.state.successful_scrapes = batch_result.successful_scrapes
            ctx.state.scraping_time = time.time() - start_time

            # Add performance stats
            ctx.state.processing_errors.append(
                f"Batch scraping: {batch_result.total_time_seconds:.2f}s total, "
                f"{batch_result.successful_scrapes}/{batch_result.total_processed} successful"
            )

            logger.info(
                f"BatchScrapeNode: Completed batch scraping - {batch_result.successful_scrapes}/{batch_result.total_processed} successful in {ctx.state.scraping_time:.2f}s"
            )

            if ctx.state.successful_scrapes == 0:
                return End(
                    {
                        "error": "All scraping attempts failed",
                        "query": ctx.state.query,
                        "urls_attempted": ctx.state.relevant_urls,
                    }
                )

            # Filter to only successful scrapes with content
            successful_results = [
                result
                for result in ctx.state.scrape_results
                if result.success
                and result.full_text_extracted
                and result.full_text_content
            ]

            if not successful_results:
                return End(
                    {
                        "error": "No scraped content available for summarization",
                        "query": ctx.state.query,
                        "successful_scrapes": ctx.state.successful_scrapes,
                    }
                )

            # Update scrape results to only successful ones with content
            ctx.state.scrape_results = successful_results
            logger.info(
                f"BatchScrapeNode: {len(successful_results)} results have content for summarization"
            )

            return BatchSummarizeNode()

        except Exception as e:
            error_msg = f"Batch scraping failed: {e}"
            ctx.state.processing_errors.append(error_msg)
            logger.error(f"BatchScrapeNode: {error_msg}")
            return End({"error": str(e), "query": ctx.state.query})


@dataclass
class BatchSummarizeNode(
    BaseNode[
        GoogleSearchScrapeState,
        GoogleSearchScrapeAnswerDeps,
        Union["AnswerNode", End],
    ]
):
    """Summarize all scraped results in a single API call"""

    async def run(
        self,
        ctx: GraphRunContext[GoogleSearchScrapeState, GoogleSearchScrapeAnswerDeps],
    ) -> Union["AnswerNode", End]:
        logger.info(
            f"BatchSummarizeNode: Batch summarizing {len(ctx.state.scrape_results)} scraped results"
        )

        if not ctx.state.scrape_results:
            return End(
                {"error": "No scrape results to summarize", "query": ctx.state.query}
            )

        try:
            import time

            start_time = time.time()

            # Use simplified summarization API with list of results
            logger.info(
                f"BatchSummarizeNode: Using simplified API to summarize {len(ctx.state.scrape_results)} results"
            )

            # Execute batch summarization with simplified function
            summary_result = await summarize_content(
                ctx.state.scrape_results,  # Pass the list directly
                max_length=2000,
            )

            # Handle both single and multiple results from simplified API
            if hasattr(summary_result, "results"):
                # Got SummarizedResults with multiple summaries
                ctx.state.summaries = summary_result.results
            else:
                # Got single SummarizedResult - convert to list
                ctx.state.summaries = [summary_result]

            ctx.state.summarization_time = time.time() - start_time

            logger.info(
                f"BatchSummarizeNode: Successfully generated {len(ctx.state.summaries)} summaries in {ctx.state.summarization_time:.2f}s"
            )

            ctx.state.processing_errors.append(
                f"Batch summarization: {len(ctx.state.summaries)} summaries in {ctx.state.summarization_time:.2f}s (simplified API)"
            )

            return AnswerNode()

        except Exception as e:
            error_msg = f"Batch summarization failed: {e}"
            ctx.state.processing_errors.append(error_msg)
            logger.error(f"BatchSummarizeNode: {error_msg}")
            return End({"error": str(e), "query": ctx.state.query})


@dataclass
class AnswerNode(BaseNode[GoogleSearchScrapeState, GoogleSearchScrapeAnswerDeps, End]):
    """Generate final answer from batch summaries"""

    async def run(
        self,
        ctx: GraphRunContext[GoogleSearchScrapeState, GoogleSearchScrapeAnswerDeps],
    ) -> End:
        logger.info(
            f"AnswerNode: Generating final answer from {len(ctx.state.summaries)} summaries"
        )

        try:
            import time

            start_time = time.time()

            # Extract key information from summaries
            key_points = []
            sources = []

            for summary in ctx.state.summaries:
                key_points.extend(summary.key_findings)
                sources.append(summary.source_url)

            # Create comprehensive answer by combining insights
            summary_texts = [
                f"- {summary.title}: {summary.summary}"
                for summary in ctx.state.summaries
            ]

            answer_text = f"""Based on analysis of {len(ctx.state.summaries)} web sources, here's what I found regarding "{ctx.state.query}":

{chr(10).join(summary_texts)}

Key insights: {"; ".join(key_points[:5])}"""  # Top 5 key points

            # Calculate confidence based on source quality
            avg_confidence = sum(
                summary.confidence_score for summary in ctx.state.summaries
            ) / len(ctx.state.summaries)

            ctx.state.final_answer = FinalAnswer(
                answer=answer_text,
                key_points=key_points[:10],  # Top 10 key points
                sources=sources,
                confidence=avg_confidence,
                total_sources_found=len(ctx.state.search_results),
                successful_scrapes=ctx.state.successful_scrapes,
                summaries_generated=len(ctx.state.summaries),
            )

            ctx.state.total_processing_time = (
                time.time()
                - start_time
                + ctx.state.scraping_time
                + ctx.state.summarization_time
            )

            logger.info(
                f"AnswerNode: Generated final answer with {len(sources)} sources in {ctx.state.total_processing_time:.2f}s total"
            )

            return End(
                {
                    "success": True,
                    "query": ctx.state.query,
                    "answer": ctx.state.final_answer.model_dump(),
                    "processing_stats": {
                        "total_time": ctx.state.total_processing_time,
                        "scraping_time": ctx.state.scraping_time,
                        "summarization_time": ctx.state.summarization_time,
                        "sources_found": len(ctx.state.search_results),
                        "successful_scrapes": ctx.state.successful_scrapes,
                        "summaries_generated": len(ctx.state.summaries),
                        "processing_errors": ctx.state.processing_errors,
                    },
                }
            )

        except Exception as e:
            error_msg = f"Answer generation failed: {e}"
            ctx.state.processing_errors.append(error_msg)
            logger.error(f"AnswerNode: {error_msg}")
            return End({"error": str(e), "query": ctx.state.query})


# === GOOGLE SEARCH GRAPH ASSEMBLY ===

google_search_scrape_answer_graph = Graph(
    nodes=[
        GoogleSearchNode,
        BatchScrapeNode,
        BatchSummarizeNode,
        AnswerNode,
    ]
)


async def google_search_scrape_answer(
    query: str, max_results: int = 10, max_scrape_urls: int = 5
) -> Dict[str, Any]:
    """
    Google search -> batch scrape -> batch summarize -> answer workflow.

    Uses Google Custom Search Engine to find relevant web content, then:
    1. Scrapes content from found URLs using browser pooling
    2. Summarizes all content in a single API call
    3. Generates comprehensive answer with sources and metadata

    Args:
        query: Search query for Google Custom Search
        max_results: Maximum search results to consider
        max_scrape_urls: Maximum URLs to scrape

    Returns:
        Complete answer with sources, summaries, and performance stats
    """

    # Initialize dependencies
    deps = GoogleSearchScrapeAnswerDeps()

    # Initial state
    initial_state = GoogleSearchScrapeState(
        query=query, max_results=max_results, max_scrape_urls=max_scrape_urls
    )

    # Run the Google search workflow
    result = await google_search_scrape_answer_graph.run(
        GoogleSearchNode(),
        state=initial_state,
        deps=deps,
    )

    return result.output


# Export the Google search workflow
__all__ = [
    "google_search_scrape_answer_graph",
    "google_search_scrape_answer",
    "GoogleSearchScrapeState",
    "GoogleSearchScrapeAnswerDeps",
    "FinalAnswer",
]
