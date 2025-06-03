"""
Search -> Batch Scrape -> Batch Summarize -> Answer Graph (V2)

Complete rewrite using the new batch capabilities:
1. SearchNode: Find relevant URLs using web search
2. BatchScrapeNode: Scrape all URLs efficiently with browser pooling
3. BatchSummarizeNode: Summarize all results in a single API call
4. AnswerNode: Generate final answer from batch summaries

This eliminates multiple API calls and uses our optimized batch processing.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from pydantic_scrape.agents.search import SearchTaskAndResults, _search_agent

# Import batch summarization
from pydantic_scrape.agents.summarization import (
    SummarizationContext,
    SummarizedResult,
    summarize_content,
)

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


# State for the optimized batch workflow
@dataclass
class OptimizedSearchScrapeState:
    """State for the complete optimized search -> batch scrape -> batch summarize workflow"""

    # Input
    query: str
    max_results: int = 10
    max_scrape_urls: int = 5

    # Search phase
    search_results: List[SearchTaskAndResults] = None
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
class OptimizedSearchScrapeAnswerDeps:
    """Dependencies for the optimized workflow"""

    # No dependencies needed - we'll use the search agent directly


# === OPTIMIZED GRAPH NODES ===


@dataclass
class SearchNode(
    BaseNode[
        OptimizedSearchScrapeState,
        OptimizedSearchScrapeAnswerDeps,
        Union["BatchScrapeNode", End],
    ]
):
    """Find relevant URLs using search"""

    async def run(
        self,
        ctx: GraphRunContext[
            OptimizedSearchScrapeState, OptimizedSearchScrapeAnswerDeps
        ],
    ) -> Union["BatchScrapeNode", End]:
        logger.info(f"SearchNode: Starting search for '{ctx.state.query}'")

        try:
            # Use sophisticated agentic search with the agent directly
            logger.info("SearchNode: Using agentic search with AI-driven strategy")

            # Create search context
            context = SearchTaskAndResults(query=ctx.state.query, max_iterations=3)

            # Run the search agent directly
            search_result = await _search_agent.run(
                f"Search for scientific content about: {ctx.state.query}",
                deps=context,
            )

            search_results = (
                context.results
            )  # Get results from context, not agent output
            logger.info(
                f"SearchNode: Agentic search completed - {len(search_results)} results"
            )

            ctx.state.search_results = search_results

            if not search_results:
                return End(
                    {"error": "No search results found", "query": ctx.state.query}
                )

            # Debug: Check what's in search results
            logger.info(
                f"SearchNode: Debug - First result type: {type(search_results[0]) if search_results else 'No results'}"
            )
            if search_results:
                first_result = search_results[0]
                logger.info(
                    f"SearchNode: Debug - First result attributes: {dir(first_result)}"
                )
                logger.info(f"SearchNode: Debug - First result: {first_result}")

            # Extract URLs from search results (limit to max_scrape_urls)
            extracted_urls = []
            for i, result in enumerate(search_results[: ctx.state.max_scrape_urls]):
                logger.info(f"SearchNode: Debug - Result {i}: {result}")
                if hasattr(result, "url") and result.url:
                    extracted_urls.append(result.url)
                    logger.info(f"SearchNode: Debug - Added URL: {result.url}")
                elif hasattr(result, "href") and result.href:
                    extracted_urls.append(result.href)
                    logger.info(f"SearchNode: Debug - Added href: {result.href}")
                else:
                    logger.warning(
                        f"SearchNode: Debug - No URL found in result {i}: {result}"
                    )

            ctx.state.relevant_urls = extracted_urls

            logger.info(
                f"SearchNode: Found {len(ctx.state.relevant_urls)} URLs to scrape"
            )
            return BatchScrapeNode()

        except Exception as e:
            error_msg = f"search failed: {e}"
            ctx.state.processing_errors.append(error_msg)
            logger.error(f"SearchNode: {error_msg}")
            return End({"error": str(e), "query": ctx.state.query})


@dataclass
class BatchScrapeNode(
    BaseNode[
        OptimizedSearchScrapeState,
        OptimizedSearchScrapeAnswerDeps,
        Union["BatchSummarizeNode", End],
    ]
):
    """Scrape all URLs efficiently using browser pooling"""

    async def run(
        self,
        ctx: GraphRunContext[
            OptimizedSearchScrapeState, OptimizedSearchScrapeAnswerDeps
        ],
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
        OptimizedSearchScrapeState,
        OptimizedSearchScrapeAnswerDeps,
        Union["AnswerNode", End],
    ]
):
    """Summarize all scraped results in a single API call"""

    async def run(
        self,
        ctx: GraphRunContext[
            OptimizedSearchScrapeState, OptimizedSearchScrapeAnswerDeps
        ],
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
                max_length=2000
            )

            # Handle both single and multiple results from simplified API
            if hasattr(summary_result, 'results'):
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
class AnswerNode(
    BaseNode[OptimizedSearchScrapeState, OptimizedSearchScrapeAnswerDeps, End]
):
    """Generate final answer from batch summaries"""

    async def run(
        self,
        ctx: GraphRunContext[
            OptimizedSearchScrapeState, OptimizedSearchScrapeAnswerDeps
        ],
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

            answer_text = f"""Based on analysis of {len(ctx.state.summaries)} sources, here's what I found regarding "{ctx.state.query}":

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


# === OPTIMIZED GRAPH ASSEMBLY ===

optimized_search_scrape_answer_graph = Graph(
    nodes=[
        SearchNode,
        BatchScrapeNode,
        BatchSummarizeNode,
        AnswerNode,
    ]
)


async def optimized_search_scrape_answer(
    query: str, max_results: int = 10, max_scrape_urls: int = 5, use_agent: bool = False
) -> Dict[str, Any]:
    """
    Optimized search -> batch scrape -> batch summarize -> answer workflow.

    Key optimizations:
    1. Batch scraping with browser pooling (eliminates browser overhead)
    2. Single API call for batch summarization (eliminates multiple API calls)
    3. Efficient resource management and concurrent processing
    4. Structured final answer with comprehensive metadata
    5. Direct agent usage without wrapper dependencies

    Args:
        query: Search query
        max_results: Maximum search results to consider
        max_scrape_urls: Maximum URLs to scrape
        use_agent: Whether to use agentic search

    Returns:
        Complete answer with sources, summaries, and performance stats
    """

    # No dependencies needed - agents are used directly
    deps = OptimizedSearchScrapeAnswerDeps()

    # Initial state
    initial_state = OptimizedSearchScrapeState(
        query=query, max_results=max_results, max_scrape_urls=max_scrape_urls
    )

    # Run the optimized workflow
    result = await optimized_search_scrape_answer_graph.run(
        SearchNode(),
        state=initial_state,
        deps=deps,
    )

    return result.output


# Export the optimized workflow
__all__ = [
    "optimized_search_scrape_answer_graph",
    "optimized_search_scrape_answer",
    "OptimizedSearchScrapeState",
    "OptimizedSearchScrapeAnswerDeps",
    "FinalAnswer",
]
