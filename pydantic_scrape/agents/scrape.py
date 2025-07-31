"""
Intelligent Scrape Agent - AI-powered decision making for web scraping

This agent can:
1. Analyze if a URL is relevant to extract information
2. Make intelligent decisions about what to scrape
3. Extract specific data based on instructions
4. Return structured results or skip irrelevant pages
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from pydantic_scrape.dependencies.fetch import FetchDependency


class ScrapeDecision(BaseModel):
    """Decision about whether to scrape a page"""

    should_scrape: bool = Field(description="Whether this page should be scraped")
    relevance_score: float = Field(description="Relevance score 0-1", ge=0.0, le=1.0)
    reason: str = Field(description="Why this decision was made")
    key_indicators: List[str] = Field(
        description="Key indicators found", default_factory=list
    )


class ScrapeResult(BaseModel):
    """Result from scraping a page"""

    url: str = Field(description="The URL that was scraped")
    title: str = Field(description="Page title", default="")
    extracted_data: Dict[str, Any] = Field(
        description="Extracted structured data", default_factory=dict
    )
    key_points: List[str] = Field(description="Key points found", default_factory=list)
    relevance_score: float = Field(
        description="How relevant was this page", ge=0.0, le=1.0, default=0.5
    )
    content_snippet: str = Field(
        description="Brief snippet of relevant content", default=""
    )
    scrape_successful: bool = Field(
        description="Whether scraping was successful", default=False
    )
    error_message: str = Field(
        description="Error message if scraping failed", default=""
    )


@dataclass
class ScrapeContext:
    """Context for the intelligent scrape agent"""

    url: str
    instructions: str
    html_content: str = ""
    soup: Optional[BeautifulSoup] = None
    fetch_successful: bool = False
    decision_made: Optional[ScrapeDecision] = None
    final_result: Optional[ScrapeResult] = None


# Create the intelligent scrape agent
scrape_agent = Agent(
    "openai:gpt-4o",
    deps_type=ScrapeContext,
    output_type=ScrapeResult,
    system_prompt="""You are an intelligent web scraping agent. Your job is to:

1. ANALYZE the HTML content to determine if it's relevant to the user's instructions
2. DECIDE whether to extract data or skip the page
3. EXTRACT specific information when relevant
4. RETURN structured results

You have these tools available:
- analyze_page_relevance: Determine if page is worth scraping
- extract_structured_data: Extract specific data from relevant pages

WORKFLOW:
1. First call analyze_page_relevance to check if the page is relevant
2. If relevant, call extract_structured_data to get the information
3. Return a complete ScrapeResult with your findings

Be selective - don't scrape irrelevant pages. Focus on quality over quantity.""",
)


@scrape_agent.tool
async def analyze_page_relevance(
    ctx: RunContext[ScrapeContext], quick_analysis: str
) -> str:
    """
    Analyze if this page is relevant to the scraping instructions.

    Args:
        quick_analysis: Your analysis of why this page is/isn't relevant

    Returns:
        Decision result
    """
    try:
        # Parse the HTML if not already done
        if not ctx.deps.soup and ctx.deps.html_content:
            ctx.deps.soup = BeautifulSoup(ctx.deps.html_content, "html.parser")

        if not ctx.deps.soup:
            ctx.deps.decision_made = ScrapeDecision(
                should_scrape=False,
                relevance_score=0.0,
                reason="No HTML content available to analyze",
                key_indicators=[],
            )
            return "L No HTML content - cannot analyze relevance"

        # Get page title and key content for analysis
        title = ctx.deps.soup.find("title")
        title_text = title.get_text(strip=True) if title else ""

        # Get main content indicators
        headers = [
            h.get_text(strip=True)
            for h in ctx.deps.soup.find_all(["h1", "h2", "h3"])[:5]
        ]

        # Get some body text for context
        body_text = ""
        body = ctx.deps.soup.find("body")
        if body:
            # Get first few paragraphs
            paragraphs = body.find_all("p")[:3]
            body_text = " ".join([p.get_text(strip=True) for p in paragraphs])
            body_text = body_text[:500]  # Limit length

        # Simple relevance scoring based on content
        instructions_lower = ctx.deps.instructions.lower()
        title_lower = title_text.lower()
        headers_text = " ".join(headers).lower()
        body_lower = body_text.lower()

        # Count keyword matches
        instruction_words = instructions_lower.split()
        matches = 0
        key_indicators = []

        for word in instruction_words:
            if len(word) > 3:  # Skip short words
                if word in title_lower:
                    matches += 3  # Title matches are more important
                    key_indicators.append(f"Title contains '{word}'")
                elif word in headers_text:
                    matches += 2  # Header matches are important
                    key_indicators.append(f"Headers contain '{word}'")
                elif word in body_lower:
                    matches += 1  # Body matches are less important
                    key_indicators.append(f"Content contains '{word}'")

        # Calculate relevance score
        max_possible_matches = len([w for w in instruction_words if len(w) > 3]) * 3
        relevance_score = (
            min(matches / max(max_possible_matches, 1), 1.0)
            if max_possible_matches > 0
            else 0.0
        )

        # Decide whether to scrape
        should_scrape = relevance_score > 0.2  # Threshold for scraping

        reason = f"Analysis: {quick_analysis}. Found {matches} keyword matches. "
        if should_scrape:
            reason += f"Relevance score {relevance_score:.2f} - worth scraping."
        else:
            reason += f"Relevance score {relevance_score:.2f} - not relevant enough."

        ctx.deps.decision_made = ScrapeDecision(
            should_scrape=should_scrape,
            relevance_score=relevance_score,
            reason=reason,
            key_indicators=key_indicators,
        )

        logger.info(
            f"ScrapeAgent: Relevance analysis for {ctx.deps.url[:50]}... - Score: {relevance_score:.2f}, Scrape: {should_scrape}"
        )

        return (
            f" Relevance Analysis Complete:\n"
            f"Should Scrape: {should_scrape}\n"
            f"Relevance Score: {relevance_score:.2f}\n"
            f"Key Indicators: {', '.join(key_indicators[:3])}\n"
            f"Reason: {reason}"
        )

    except Exception as e:
        error_msg = f"Error analyzing page relevance: {e}"
        logger.error(f"ScrapeAgent: {error_msg}")
        ctx.deps.decision_made = ScrapeDecision(
            should_scrape=False,
            relevance_score=0.0,
            reason=error_msg,
            key_indicators=[],
        )
        return f"L Analysis failed: {error_msg}"


@scrape_agent.tool
async def extract_structured_data(
    ctx: RunContext[ScrapeContext], extraction_strategy: str
) -> str:
    """
    Extract structured data from the page.

    Args:
        extraction_strategy: Your strategy for extracting the data

    Returns:
        Extraction result
    """
    try:
        if not ctx.deps.soup:
            return "L No HTML content available for extraction"

        if not ctx.deps.decision_made or not ctx.deps.decision_made.should_scrape:
            return (
                "L Page was not marked for scraping - call analyze_page_relevance first"
            )

        # Extract basic information
        title = ctx.deps.soup.find("title")
        title_text = title.get_text(strip=True) if title else "No title found"

        # Extract key content based on instructions
        extracted_data = {}
        key_points = []

        # Get main headers
        headers = ctx.deps.soup.find_all(["h1", "h2", "h3", "h4"])
        if headers:
            extracted_data["headers"] = [h.get_text(strip=True) for h in headers[:10]]
            key_points.extend([h.get_text(strip=True) for h in headers[:3]])

        # Get main content paragraphs
        paragraphs = ctx.deps.soup.find_all("p")
        if paragraphs:
            content_text = []
            for p in paragraphs[:10]:  # Limit to first 10 paragraphs
                text = p.get_text(strip=True)
                if len(text) > 50:  # Only substantial paragraphs
                    content_text.append(text)
            extracted_data["main_content"] = content_text

        # Extract lists if present
        lists = ctx.deps.soup.find_all(["ul", "ol"])
        if lists:
            list_items = []
            for ul in lists[:3]:  # First 3 lists
                items = [li.get_text(strip=True) for li in ul.find_all("li")[:5]]
                list_items.extend(items)
            if list_items:
                extracted_data["list_items"] = list_items
                key_points.extend(list_items[:3])

        # Look for specific patterns based on instructions
        instructions_lower = ctx.deps.instructions.lower()

        # If looking for links
        if "link" in instructions_lower or "url" in instructions_lower:
            links = ctx.deps.soup.find_all("a", href=True)
            if links:
                extracted_data["links"] = [
                    {"text": link.get_text(strip=True), "url": link.get("href")}
                    for link in links[:10]
                    if link.get_text(strip=True)
                ]

        # If looking for images
        if "image" in instructions_lower or "photo" in instructions_lower:
            images = ctx.deps.soup.find_all("img", src=True)
            if images:
                extracted_data["images"] = [
                    {"alt": img.get("alt", ""), "src": img.get("src")}
                    for img in images[:5]
                ]

        # Create content snippet from first paragraph or key content
        content_snippet = ""
        if "main_content" in extracted_data and extracted_data["main_content"]:
            content_snippet = extracted_data["main_content"][0][:200] + "..."
        elif key_points:
            content_snippet = key_points[0][:200] + "..."
        else:
            content_snippet = title_text[:200] + "..."

        # Create the final result
        ctx.deps.final_result = ScrapeResult(
            url=ctx.deps.url,
            title=title_text,
            extracted_data=extracted_data,
            key_points=key_points[:5],  # Top 5 key points
            relevance_score=ctx.deps.decision_made.relevance_score,
            content_snippet=content_snippet,
            scrape_successful=True,
            error_message="",
        )

        logger.info(
            f"ScrapeAgent: Successfully extracted data from {ctx.deps.url[:50]}... - {len(extracted_data)} data categories"
        )

        return (
            f" Data Extraction Complete:\n"
            f"Strategy: {extraction_strategy}\n"
            f"Title: {title_text[:100]}...\n"
            f"Data Categories: {list(extracted_data.keys())}\n"
            f"Key Points: {len(key_points)}\n"
            f"Content Snippet: {content_snippet[:150]}..."
        )

    except Exception as e:
        error_msg = f"Error extracting data: {e}"
        logger.error(f"ScrapeAgent: {error_msg}")

        ctx.deps.final_result = ScrapeResult(
            url=ctx.deps.url,
            title="",
            extracted_data={},
            key_points=[],
            relevance_score=0.0,
            content_snippet="",
            scrape_successful=False,
            error_message=error_msg,
        )

        return f"L Extraction failed: {error_msg}"


async def intelligent_scrape(
    url: str, instructions: str, timeout: int = 30
) -> ScrapeResult:
    """
    Intelligently scrape a URL based on specific instructions.

    Args:
        url: URL to scrape
        instructions: Specific instructions about what to look for
        timeout: Timeout for fetching the page

    Returns:
        ScrapeResult with extracted data or decision to skip
    """
    try:
        logger.info(f"ScrapeAgent: Starting intelligent scrape of {url[:50]}...")

        # Initialize context
        context = ScrapeContext(url=url, instructions=instructions)

        # Fetch the page content
        fetch_dep = FetchDependency()
        fetch_result = await fetch_dep.fetch_content(url)

        if fetch_result.error or not fetch_result.content:
            return ScrapeResult(
                url=url,
                title="",
                extracted_data={},
                key_points=[],
                relevance_score=0.0,
                content_snippet="",
                scrape_successful=False,
                error_message=f"Failed to fetch content: {fetch_result.error or 'No content returned'}",
            )

        context.html_content = fetch_result.content
        context.fetch_successful = True

        # Run the AI agent to make intelligent decisions
        prompt = f"""Analyze this URL and extract relevant information:

URL: {url}
Instructions: {instructions}

First determine if this page is relevant, then extract the requested information if it is."""

        result = await scrape_agent.run(prompt, deps=context)

        # Return the agent's result
        if context.final_result:
            return context.final_result
        else:
            # If no final result, create a basic one from the agent output
            return result.output

    except Exception as e:
        error_msg = f"Intelligent scrape failed: {e}"
        logger.error(f"ScrapeAgent: {error_msg}")

        return ScrapeResult(
            url=url,
            title="",
            extracted_data={},
            key_points=[],
            relevance_score=0.0,
            content_snippet="",
            scrape_successful=False,
            error_message=error_msg,
        )


async def batch_intelligent_scrape(
    urls_and_instructions: List[tuple[str, str]], max_concurrent: int = 3
) -> List[ScrapeResult]:
    """
    Run intelligent scraping on multiple URLs in parallel.

    Args:
        urls_and_instructions: List of (url, instructions) tuples
        max_concurrent: Maximum concurrent scraping tasks

    Returns:
        List of ScrapeResults
    """
    logger.info(
        f"ScrapeAgent: Starting batch scrape of {len(urls_and_instructions)} URLs with {max_concurrent} concurrent tasks"
    )

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scrape_with_semaphore(url: str, instructions: str) -> ScrapeResult:
        async with semaphore:
            return await intelligent_scrape(url, instructions)

    # Run all scraping tasks
    tasks = [
        scrape_with_semaphore(url, instructions)
        for url, instructions in urls_and_instructions
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error results
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            url = urls_and_instructions[i][0]
            final_results.append(
                ScrapeResult(
                    url=url,
                    title="",
                    extracted_data={},
                    key_points=[],
                    relevance_score=0.0,
                    content_snippet="",
                    scrape_successful=False,
                    error_message=f"Task failed: {str(result)}",
                )
            )
        else:
            final_results.append(result)

    # Log summary
    successful = len([r for r in final_results if r.scrape_successful])
    logger.info(
        f"ScrapeAgent: Batch scrape complete - {successful}/{len(final_results)} successful"
    )

    return final_results


# Export the main functions
__all__ = [
    "scrape_agent",
    "intelligent_scrape",
    "batch_intelligent_scrape",
    "ScrapeResult",
    "ScrapeDecision",
    "ScrapeContext",
]
