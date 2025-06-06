"""
Wrapped search agent that implements the AgentProtocol
"""

from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from searchthescience import (
    SearchQuery,
    SearchResult,
    multi_search_interface,
)

load_dotenv()


@dataclass
class SearchTaskAndResults:
    """Unified context for all search agents (simple and graph-based)"""

    query: str
    results: List[SearchResult] = None

    def __post_init__(self):
        if self.results is None:
            self.results = []

    def should_stop(self) -> bool:
        """Check if search should terminate"""
        return self.satisfied or self.iterations >= self.max_iterations


# Search agent - executes searches
_search_agent = Agent(
    "openai:gpt-4o",
    deps_type=SearchTaskAndResults,
    output_type=str,
    system_prompt="""You are a search specialist. Execute 2-3 targeted searches.

AVAILABLE SEARCH TYPES:
- SCIENCE_GENERAL: Scientific papers from OpenAlex
- SCIENCE_ARXIV: Preprints from arXiv  
- ZENODO: Research outputs from Zenodo repository

Create different search queries using these stable search types. Read the results, get new search terms from what you find, and keep going until you are happy with the results.
In your final answer, please answer the question with references rather than just listing the search results.""",
)


@_search_agent.tool
async def execute_searches(
    ctx: RunContext[SearchTaskAndResults], queries: List[SearchQuery]
) -> str:
    """Execute the search queries."""
    try:
        results = await multi_search_interface(
            search_queries=queries, max_results=5, rerank=True
        )
        valid_results = [r for r in results if not isinstance(r, Exception)]
        ctx.deps.results.extend(valid_results)
        return [result.model_dump() for result in ctx.deps.results]
    except Exception as e:
        return f"❌ Search failed: {str(e)}"


@_search_agent.tool
async def prune_results(
    ctx: RunContext[SearchTaskAndResults],
    indices_to_remove: List[int],
    reason: str,
    satisfied: bool = False,
) -> str:
    """Remove irrelevant results and optionally mark search as satisfied"""
    try:
        # Remove results (reverse order to avoid index shifting)
        for idx in sorted(indices_to_remove, reverse=True):
            if 0 <= idx < len(ctx.deps.results):
                removed = ctx.deps.results[idx]
                print(f"removing {removed} because {reason}")
                ctx.deps.results.pop(idx)

        status = "satisfied" if satisfied else "continuing"
        return f"✂️ Removed {len(indices_to_remove)} results: {reason}. Status: {status}"

    except Exception as e:
        return f"❌ Pruning failed: {str(e)}"
