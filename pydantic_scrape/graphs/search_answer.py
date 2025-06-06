"""
Simple Search -> Answer Graph

Fast workflow that:
1. Performs agentic search to find relevant papers
2. Summarizes search results directly (no scraping needed)
3. Generates a comprehensive answer

This bypasses all browser/scraping complexity for speed.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from pydantic_scrape.agents.search import SearchTaskAndResults, _search_agent
from pydantic_scrape.agents.summarization import summarize_content


class SearchAnswer(BaseModel):
    """Final answer with sources and metadata"""

    answer: str = Field(description="Comprehensive answer to the query")
    key_insights: List[str] = Field(
        description="Main insights from research", default_factory=list
    )
    sources: List[Dict[str, str]] = Field(
        description="Source papers with titles and URLs", default_factory=list
    )

    # Processing metadata
    total_sources_found: int = Field(
        description="Total search results found", default=0
    )
    summaries_generated: int = Field(
        description="Number of summaries created", default=0
    )
    processing_time: float = Field(
        description="Total processing time in seconds", default=0.0
    )


@dataclass
class SearchAnswerState:
    """State for the search -> answer workflow"""

    # Input
    query: str
    max_search_results: int = 10

    # Search results
    search_results: List[Any] = None  # SearchResult objects

    # Summaries
    summaries: List[Any] = None  # SummarizedResult objects
    processing_time: float = 0.0

    # Final answer
    final_answer: SearchAnswer = None

    def __post_init__(self):
        if self.search_results is None:
            self.search_results = []
        if self.summaries is None:
            self.summaries = []


@dataclass
class SearchAnswerDeps:
    """Dependencies for search answer workflow (empty - we use agents directly)"""

    pass


# === GRAPH NODES ===


@dataclass
class SearchNode(
    BaseNode[SearchAnswerState, SearchAnswerDeps, Union["SummarizeNode", End]]
):
    """Perform agentic search"""

    async def run(
        self, ctx: GraphRunContext[SearchAnswerState, SearchAnswerDeps]
    ) -> Union["SummarizeNode", End]:
        logger.info(f"SearchNode: Starting agentic search for '{ctx.state.query}'")

        try:
            start_time = time.time()

            # Create search context
            context = SearchTaskAndResults(query=ctx.state.query, max_iterations=3)

            # Run the search agent directly
            search_result = await _search_agent.run(
                f"Search for scientific content about: {ctx.state.query}",
                deps=context,
            )

            ctx.state.search_results = context.results
            search_time = time.time() - start_time

            logger.info(
                f"SearchNode: Found {len(ctx.state.search_results)} results in {search_time:.2f}s"
            )

            if not ctx.state.search_results:
                return End(
                    {"error": "No search results found", "query": ctx.state.query}
                )

            # Limit to max_search_results
            ctx.state.search_results = ctx.state.search_results[
                : ctx.state.max_search_results
            ]

            return SummarizeNode()

        except Exception as e:
            logger.error(f"SearchNode: Search failed: {e}")
            return End({"error": f"Search failed: {e}", "query": ctx.state.query})


@dataclass
class SummarizeNode(
    BaseNode[SearchAnswerState, SearchAnswerDeps, Union["AnswerNode", End]]
):
    """Summarize search results using optimized batch processing"""

    async def run(
        self, ctx: GraphRunContext[SearchAnswerState, SearchAnswerDeps]
    ) -> Union["AnswerNode", End]:
        logger.info(
            f"SummarizeNode: Creating comprehensive summary from {len(ctx.state.search_results)} search results"
        )

        try:
            start_time = time.time()

            # Combine all search results into one comprehensive text for summarization
            combined_content = "\n\n".join(
                [
                    f"=== SEARCH RESULT {i + 1} ===\n"
                    f"Title: {result.title}\n"
                    f"Source: {result.source}\n"
                    f"URL: {result.href}\n"
                    f"Description: {result.description}"
                    for i, result in enumerate(ctx.state.search_results)
                ]
            )

            # Get one comprehensive summary of all search results combined
            summary_result = await summarize_content(
                combined_content,  # Combined string of all search results
                max_length=2000,  # Longer since we're combining multiple results
            )

            # We expect a single comprehensive summary, not multiple
            if hasattr(summary_result, "results"):
                # Shouldn't happen with string input, but handle it
                ctx.state.summaries = summary_result.results
            else:
                # Expected: single comprehensive summary
                ctx.state.summaries = [summary_result]

            ctx.state.processing_time = time.time() - start_time

            logger.info(
                f"SummarizeNode: Created 1 comprehensive summary from {len(ctx.state.search_results)} search results in {ctx.state.processing_time:.2f}s"
            )

            if not ctx.state.summaries:
                return End(
                    {
                        "error": "No summaries generated",
                        "query": ctx.state.query,
                        "search_results_count": len(ctx.state.search_results),
                    }
                )

            return AnswerNode()

        except Exception as e:
            logger.error(f"SummarizeNode: Summarization failed: {e}")
            return End(
                {"error": f"Summarization failed: {e}", "query": ctx.state.query}
            )


@dataclass
class AnswerNode(BaseNode[SearchAnswerState, SearchAnswerDeps, End]):
    """Generate final comprehensive answer from summaries"""

    async def run(
        self, ctx: GraphRunContext[SearchAnswerState, SearchAnswerDeps]
    ) -> End:
        logger.info(
            f"AnswerNode: Generating answer from {len(ctx.state.summaries)} summaries"
        )

        try:
            # Extract key insights from all summaries
            all_insights = []
            sources = []

            for summary in ctx.state.summaries:
                all_insights.extend(summary.key_findings)
                sources.append(
                    {
                        "title": summary.title,
                        "url": summary.source_url,
                        "summary": summary.summary,
                    }
                )

            # Create comprehensive answer by combining summaries
            answer_parts = [
                f"Based on analysis of {len(ctx.state.summaries)} scientific sources, here's what the research shows about '{ctx.state.query}':",
                "",
            ]

            # Add individual paper insights
            for i, summary in enumerate(ctx.state.summaries, 1):
                answer_parts.append(f"{i}. **{summary.title}**")
                answer_parts.append(f"   {summary.summary}")
                if summary.key_findings:
                    answer_parts.append(
                        f"   Key findings: {'; '.join(summary.key_findings[:3])}"
                    )
                answer_parts.append("")

            # Add overall conclusions
            answer_parts.extend(
                [
                    "## Overall Research Insights:",
                    *[
                        f"• {insight}" for insight in all_insights[:10]
                    ],  # Top 10 insights
                ]
            )

            final_answer_text = "\n".join(answer_parts)

            # Create final answer object
            ctx.state.final_answer = SearchAnswer(
                answer=final_answer_text,
                key_insights=all_insights[:10],  # Top 10
                sources=sources,
                total_sources_found=len(ctx.state.search_results),
                summaries_generated=len(ctx.state.summaries),
                processing_time=ctx.state.processing_time,
            )

            logger.info(
                f"AnswerNode: Generated comprehensive answer with {len(sources)} sources"
            )

            return End(
                {
                    "success": True,
                    "query": ctx.state.query,
                    "answer": ctx.state.final_answer.model_dump(),
                    "raw_search_results": [
                        result.model_dump() for result in ctx.state.search_results
                    ],
                    "processing_stats": {
                        "search_results": len(ctx.state.search_results),
                        "summaries_generated": len(ctx.state.summaries),
                        "processing_time": ctx.state.processing_time,
                    },
                }
            )

        except Exception as e:
            logger.error(f"AnswerNode: Answer generation failed: {e}")
            return End(
                {"error": f"Answer generation failed: {e}", "query": ctx.state.query}
            )


# === GRAPH ASSEMBLY ===

search_answer_graph = Graph(nodes=[SearchNode, SummarizeNode, AnswerNode])
search_answer_graph.mermaid_code()


async def search_answer(query: str, max_search_results: int = 8) -> Dict[str, Any]:
    """
    Fast search -> summarize -> answer workflow.

    Args:
        query: Search query
        max_search_results: Maximum number of search results to process

    Returns:
        Comprehensive answer with sources and processing stats
    """

    # No dependencies needed - we use agents directly
    deps = SearchAnswerDeps()

    # Initial state
    initial_state = SearchAnswerState(
        query=query, max_search_results=max_search_results
    )

    # Run the streamlined workflow
    result = await search_answer_graph.run(
        SearchNode(),
        state=initial_state,
        deps=deps,
    )

    return result.output


# Export the workflow
__all__ = [
    "search_answer_graph",
    "search_answer",
    "SearchAnswer",
    "SearchAnswerState",
]
