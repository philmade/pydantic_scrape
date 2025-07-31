"""
Search and Browse Agent with Memory

Uses Google search + interactive chawan browser agent for comprehensive web research.
Features automatic memory to track visited websites using dynamic instructions.

Features:
- Google Custom Search integration
- Interactive chawan browsing with parallel processing
- Automatic memory of visited domains/URLs
- Dynamic instructions that update based on memory state
"""

from typing import List, Set, Union
from urllib.parse import urlparse

from loguru import logger
from pydantic_ai import Agent, RunContext

from pydantic_scrape.agents.chawan_browse_agent import (
    ChawanBrowseTask,
    browse_sites_parallel,
)
from pydantic_scrape.dependencies.google_search import (
    GoogleCustomSearchClient,
    SearchRequest,
)


class SearchAndBrowseAgent:
    """Search and browse agent with automatic memory via dynamic instructions."""

    def __init__(self, enable_js: bool = True, timeout: int = 30, debug: bool = False):
        self.enable_js = enable_js
        self.timeout = timeout
        self.debug = debug
        self.google_client = GoogleCustomSearchClient()

        # Memory system - track visited domains/URLs and search queries
        self.visited_domains: Set[str] = set()
        self.visited_urls: Set[str] = set()
        self.search_queries: List[str] = []

        # Create the agent with dynamic instructions and deps_type for user brief
        self.agent = Agent[Union[str, bool], str](
            "openai:gpt-4o",
            tools=[self._enhanced_search, self._browse_sites_parallel],
            system_prompt="""You are an intelligent search and browse agent with MEMORY. You search, based on the brief, then browse the websites you find, then use those ideas to prompt more forensic searches""",
            deps_type=str,
        )

        # Dynamic instructions that update based on memory state and user brief
        @self.agent.instructions
        def memory_aware_instructions(ctx: RunContext[str]) -> str:
            user_brief = ctx.deps

            # Domain memory
            domain_memory = ""
            if self.visited_domains:
                domains_list = ", ".join(sorted(self.visited_domains))
                domain_memory = f"""
🧠 VISITED DOMAINS: {domains_list}
⚠️  NEVER visit these domains again! ({len(self.visited_domains)} domains, {len(self.visited_urls)} URLs visited)
"""
            else:
                domain_memory = "🧠 VISITED DOMAINS: None yet."

            # Query memory
            query_memory = ""
            if self.search_queries:
                recent_queries = self.search_queries[-5:]  # Show last 5 queries
                query_list = "\n".join([f"  - \"{q}\"" for q in recent_queries])
                query_memory = f"""
🔍 RECENT SEARCH QUERIES ({len(self.search_queries)} total):
{query_list}
⚠️  Avoid repeating these exact queries! Use different keywords/approaches.
"""
            else:
                query_memory = "🔍 SEARCH QUERIES: None yet."

            return f"""📋 USER BRIEF: {user_brief}

{domain_memory}
{query_memory}

TOOLS AVAILABLE:
1. enhanced_search(request): Google search with shopping, web, image, news
2. browse_sites_parallel(urls, objectives): Browse multiple sites simultaneously

SEARCH STRATEGY:
- Use enhanced_search() with SearchRequest objects for targeted results
- Browse some of the sites you find and look specifically for things
- Use what you find to inspire new queries, and repeat the process

BROWSING STRATEGY:
- CRITICAL: Never browse domains you've already visited (see memory above)
- Use browse_sites_parallel() for efficiency when you have multiple URLs
- Follow the user's specific requirements carefully


Return a string with findings, or True when completely finished."""

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL for memory tracking."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return url.lower()

    def _record_visits(self, urls: List[str]) -> None:
        """Record visits to multiple URLs and their domains."""
        for url in urls:
            domain = self._extract_domain(url)
            self.visited_urls.add(url.lower())
            self.visited_domains.add(domain)
            logger.info(f"📝 Recorded visit to {domain} ({url})")

    async def _enhanced_search(self, request: SearchRequest) -> str:
        """
        Perform enhanced search with rich filtering and structured results.

        This unified search interface supports:
        - Web search (general results)
        - Shopping search (products, prices, reviews)
        - Image and news search
        - Advanced filtering (location, sites, dates, prices)

        Args:
            request: SearchRequest with all search parameters and filters

        Returns:
            String with formatted search results and metadata
        """
        try:
            logger.info(f"🔍 Enhanced {request.search_type} search: '{request.query}'")
            
            # Record the search query
            self.search_queries.append(request.query)

            results = await self.google_client.enhanced_search(request)

            if not results.results:
                return f"No {request.search_type} search results found for: {request.query}"

            # Format results for AI consumption
            formatted_results = []
            formatted_results.append(
                f"=== ENHANCED {request.search_type.upper()} SEARCH RESULTS ==="
            )
            formatted_results.append(f"Query: {results.query_used}")
            formatted_results.append(
                f"Results: {len(results.results)} of {results.total_found:,} found"
            )
            formatted_results.append(f"Search time: {results.search_time:.2f}s")
            formatted_results.append("")

            for i, result in enumerate(results.results, 1):
                formatted_results.append(f"{i}. {result.title}")
                formatted_results.append(f"   URL: {result.url}")
                formatted_results.append(f"   Snippet: {result.snippet}")

                # Add shopping-specific information
                if result.price and request.search_type == "shopping":
                    price_info = result.price
                    if price_info.get("value"):
                        formatted_results.append(
                            f"   💰 Price: {price_info['currency']} {price_info['value']}"
                        )
                    if price_info.get("availability"):
                        formatted_results.append(
                            f"   📦 Availability: {price_info['availability']}"
                        )

                # Add organization information
                if result.organization:
                    org = result.organization
                    if org.get("name"):
                        formatted_results.append(f"   🏢 Organization: {org['name']}")
                    if org.get("telephone"):
                        formatted_results.append(f"   📞 Phone: {org['telephone']}")

                # Add rating information
                if result.rating:
                    rating = result.rating
                    if rating.get("value") and rating.get("count"):
                        formatted_results.append(
                            f"   ⭐ Rating: {rating['value']}/5 ({rating['count']} reviews)"
                        )

                formatted_results.append("")

            formatted_results.append("=== END SEARCH RESULTS ===")

            final_result = "\n".join(formatted_results)
            logger.info(f"✅ Enhanced search completed: {len(results.results)} results")
            return final_result

        except Exception as e:
            logger.error(f"❌ Enhanced search failed: {e}")
            return f"Enhanced search failed: {str(e)}"

    async def _browse_sites_parallel(
        self, urls: List[str], objectives: List[str], max_actions: int = 10
    ) -> str:
        """
        Browse multiple websites in parallel using chawan browser automation.

        Args:
            urls: List of URLs to browse
            objectives: List of objectives for each URL (must match length of urls)
            max_actions: Maximum number of actions per site (default 10)

        Returns:
            String with comprehensive browsing results from all sites
        """
        try:
            if len(urls) != len(objectives):
                return "Error: Number of URLs must match number of objectives"

            logger.info(f"🚀 Starting parallel browse of {len(urls)} sites")

            # Record all URLs in memory
            self._record_visits(urls)

            # Create browsing tasks
            tasks = [
                ChawanBrowseTask(
                    url=url,
                    objective=objective,
                    max_actions=max_actions,
                    timeout=self.timeout,
                )
                for url, objective in zip(urls, objectives, strict=False)
            ]

            # Execute parallel browsing
            results = await browse_sites_parallel(
                tasks=tasks,
                enable_js=self.enable_js,
                debug=self.debug,
                timeout=self.timeout,
            )

            # Combine results
            combined_results = []
            for i, (url, objective, result) in enumerate(
                zip(urls, objectives, results, strict=False)
            ):
                combined_results.append(f"""
=== SITE {i + 1}: {url} ===
Objective: {objective}
Result:
{result}
{"=" * 50}
""")

            final_result = "\n".join(combined_results)
            logger.info(f"✅ Completed parallel browse of {len(urls)} sites")
            return final_result

        except Exception as e:
            logger.error(f"❌ Parallel browse failed: {e}")
            return f"Failed to browse sites in parallel: {str(e)}"

    async def run(self, instruction: str) -> Union[str, bool]:
        """
        Execute a search and browse task.

        Args:
            instruction: Natural language instruction for the task

        Returns:
            Union[str, bool]: String for clarifications, True when complete
        """
        try:
            logger.info(f"🎯 Starting search and browse task: {instruction}")
            result = await self.agent.run(instruction, deps=instruction)  # Pass instruction as deps for context
            logger.info("✅ Search and browse task completed")
            return result.output

        except Exception as e:
            import traceback

            error_msg = f"Search and browse task failed: {str(e)}"
            logger.error(f"❌ {error_msg}\nFull traceback:\n{traceback.format_exc()}")
            return error_msg


async def search_and_browse(
    instruction: str, enable_js: bool = True, timeout: int = 30, debug: bool = False
) -> Union[str, bool]:
    """
    Execute a search and browse task using Google search + interactive chawan browser automation.

    Args:
        instruction: Natural language instruction for the research task
        enable_js: Enable JavaScript execution in chawan browser
        timeout: Timeout in seconds for browser operations
        debug: Enable debug logging for browsing sessions

    Returns:
        Union[str, bool]: String with research findings, True when complete
    """
    agent = SearchAndBrowseAgent(enable_js=enable_js, timeout=timeout, debug=debug)
    return await agent.run(instruction)


# Export the main functions
__all__ = ["search_and_browse", "SearchAndBrowseAgent"]
