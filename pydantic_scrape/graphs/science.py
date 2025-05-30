"""
Science scraper graph - dependencies do heavy lifting, nodes are logic gates
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ..dependencies import (
    ContentAnalysisDependency,
    ContentAnalysisResult,
    CrossrefDependency,
    FetchDependency,
    FetchResult,
    OpenAlexDependency,
    OpenAlexResult,
)


@dataclass
class ScienceDeps:
    """All dependencies for science scraping - these do the heavy lifting"""

    fetch: FetchDependency
    content_analysis: ContentAnalysisDependency
    openalex: OpenAlexDependency
    crossref: CrossrefDependency


# Lightweight logic gate nodes specific to science graph
@dataclass
class ScienceFetchNode(
    BaseNode[None, ScienceDeps, Union["ContentAnalysisNode", End[Dict]]]
):
    """Logic gate: Use fetch dependency, check if successful"""

    url: str
    browser_config: Optional[Dict] = None

    async def run(
        self, ctx: GraphRunContext[None, ScienceDeps]
    ) -> Union["ContentAnalysisNode", End[Dict]]:
        # Heavy lifting done by dependency
        result = await ctx.deps.fetch.fetch_content(
            self.url, self.browser_config or {"headless": True, "humanize": True}
        )

        # Logic gate: route based on result
        if result.error:
            return End({"error": result.error, "url": self.url})

        # Pass data to next logic gate
        return ContentAnalysisNode(fetch_result=result)


@dataclass
class ContentAnalysisNode(
    BaseNode[None, ScienceDeps, Union["OpenAlexLookupNode", End[Dict]]]
):
    """Logic gate: Use content analysis dependency, route based on result"""

    fetch_result: FetchResult

    async def run(
        self, ctx: GraphRunContext[None, ScienceDeps]
    ) -> Union["OpenAlexLookupNode", End[Dict]]:
        # Heavy lifting done by dependency
        analysis_result = await ctx.deps.content_analysis.analyze_content(
            self.fetch_result
        )

        # Light logic gate: route based on analysis
        if (
            analysis_result.content_type != "science"
            or analysis_result.confidence < 0.5
        ):
            return End(
                {
                    "type": "not_science",
                    "url": self.fetch_result.url,
                    "title": self.fetch_result.title,
                    "analysis": {
                        "detected_type": analysis_result.content_type,
                        "confidence": analysis_result.confidence,
                        "indicators": analysis_result.indicators_found,
                    },
                }
            )

        # Pass extracted data to OpenAlex lookup
        return OpenAlexLookupNode(
            fetch_result=self.fetch_result,
            analysis_result=analysis_result,
            doi=analysis_result.doi,
            title=self.fetch_result.title or "",
        )


@dataclass
class OpenAlexLookupNode(
    BaseNode[None, ScienceDeps, Union["CrossrefLookupNode", End[Dict]]]
):
    """Logic gate: Use OpenAlex dependency, decide if successful"""

    fetch_result: FetchResult
    analysis_result: ContentAnalysisResult
    doi: Optional[str]
    title: str

    async def run(
        self, ctx: GraphRunContext[None, ScienceDeps]
    ) -> Union["CrossrefLookupNode", End[Dict]]:
        # Heavy lifting done by dependency
        openalex_result = await ctx.deps.openalex.lookup(doi=self.doi, title=self.title)

        # Always continue to Crossref (even if OpenAlex failed)
        return CrossrefLookupNode(
            fetch_result=self.fetch_result,
            analysis_result=self.analysis_result,
            openalex_result=openalex_result,
            doi=self.doi
            or (openalex_result.doi if openalex_result.lookup_successful else None),
            title=self.title,
        )


@dataclass
class CrossrefLookupNode(BaseNode[None, ScienceDeps, End[Dict]]):
    """Logic gate: Use Crossref dependency, create final result"""

    fetch_result: FetchResult
    analysis_result: ContentAnalysisResult
    openalex_result: OpenAlexResult
    doi: Optional[str]
    title: str

    async def run(self, ctx: GraphRunContext[None, ScienceDeps]) -> End[Dict]:
        # Heavy lifting done by dependency
        crossref_result = await ctx.deps.crossref.lookup(doi=self.doi, title=self.title)

        # Logic gate: compose final result from all dependencies
        final_result = {
            "type": "science",
            "url": self.fetch_result.url,
            "title": self.title,
            "status_code": self.fetch_result.status_code,
            # Content analysis results
            "analysis": {
                "content_type": self.analysis_result.content_type,
                "confidence": self.analysis_result.confidence,
                "doi": self.analysis_result.doi,
                "arxiv_id": self.analysis_result.arxiv_id,
                "pubmed_id": self.analysis_result.pubmed_id,
                "indicators": self.analysis_result.indicators_found,
            },
            # OpenAlex metadata
            "openalex": {
                "success": self.openalex_result.lookup_successful,
                "authors": self.openalex_result.authors,
                "citation_count": self.openalex_result.citation_count,
                "journal": self.openalex_result.journal_name,
                "open_access": self.openalex_result.open_access_type,
            }
            if self.openalex_result
            else None,
            # Crossref metadata
            "crossref": {
                "success": crossref_result.lookup_successful,
                "doi": crossref_result.crossref_doi,
                "publisher": crossref_result.publisher,
                "publication_date": crossref_result.publication_date,
                "references_count": len(crossref_result.references),
            }
            if crossref_result
            else None,
            # Content info
            "content_length": len(self.fetch_result.content or ""),
            "fetch_duration": self.fetch_result.fetch_duration,
        }

        return End(final_result)


# Create the science graph with lightweight nodes
science_graph = Graph(
    nodes=[
        ScienceFetchNode,  # Logic gate using fetch dependency
        ContentAnalysisNode,  # Logic gate for science detection
        OpenAlexLookupNode,  # Logic gate using OpenAlex dependency
        CrossrefLookupNode,  # Logic gate using Crossref dependency
    ]
)


async def scrape_science_paper(
    url: str, browser_config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Science scraper where dependencies do heavy lifting, nodes are logic gates.

    Pattern:
    - Dependencies handle: fetching, API calls, data parsing
    - Nodes handle: routing decisions, error checking, result composition
    """

    # Dependencies do the heavy lifting
    deps = ScienceDeps(
        fetch=FetchDependency(timeout_ms=30000),
        openalex=OpenAlexDependency(fuzzy_match_threshold=85.0),
        crossref=CrossrefDependency(),
        content_analysis=ContentAnalysisDependency(),
    )

    # Lightweight starting node with just the data it needs
    starting_node = ScienceFetchNode(url=url, browser_config=browser_config)

    # Run graph - nodes are just logic gates using dependencies
    result = await science_graph.run(
        starting_node,
        state=None,  # No shared state needed
        deps=deps,  # Dependencies injected
    )

    return result.output


# Export
__all__ = ["science_graph", "scrape_science_paper"]
