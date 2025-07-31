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

from typing import Set, Union

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from pydantic_scrape.toolsets.agent_toolset import (
    browse_tasks_parallel,
)
from pydantic_scrape.toolsets.search_toolset import enhanced_search


class SearchAndBrowseTask(BaseModel):
    """Task object for search and browse operations"""

    url: str
    objective: str


class SearchAndBrowseContext(BaseModel):
    """Context for search and browse agent with memory"""

    visited_domains: Set[str] = set()
    visited_urls: Set[str] = set()
    timeout: int = 30
    debug: bool = False


# MODULE-LEVEL AGENT - Clean pattern like chawan_browse_agent
agent = Agent[Union[str, bool], SearchAndBrowseContext](
    "openai:gpt-4o",
    deps_type=SearchAndBrowseContext,
    tools=[enhanced_search, browse_tasks_parallel],
    system_prompt="""You are an intelligent search and browse agent with MEMORY.""",
)


@agent.instructions
def memory_aware_instructions(ctx: RunContext[SearchAndBrowseContext]) -> str:
    memory_text = ""
    if ctx.deps.visited_domains:
        domains_list = ", ".join(sorted(ctx.deps.visited_domains))
        memory_text = f"""
🧠 MEMORY - PREVIOUSLY VISITED DOMAINS: {domains_list}
⚠️  NEVER visit these domains again! You have already browsed them.
📊 Total domains visited: {len(ctx.deps.visited_domains)}
📊 Total URLs visited: {len(ctx.deps.visited_urls)}
"""
    else:
        memory_text = "🧠 MEMORY: No domains visited yet in this conversation."

    return f"""{memory_text}

SEARCH STRATEGY:
- Search -> Read -> Search -> Read. Repeat if neccessary.
- Get new ideas and insights from what you read. Then search and read again.
- Use enhanced_search() with SearchRequest objects for targeted results
- **CRITICAL: ALWAYS set location/country_code for geographic queries:**

BROWSING STRATEGY:
- CRITICAL: Never browse domains you've already visited (see memory above)
- Use browse_tasks_parallel() with SearchAndBrowseTask objects for efficiency
- Follow the user's specific requirements carefully

WORKFLOW:
1. Search for relevant websites using enhanced_search() with geographic targeting
   Example: enhanced_search(SearchRequest(query="cabinet refacing services", location="North West England"))
2. Filter results to exclude already-visited domains from memory
3. Select promising NEW websites only
4. Create SearchAndBrowseTask objects and browse in parallel for speed
5. Extract and synthesize findings

Return a string with findings, or True when completely finished."""


class SearchAndBrowseAgent:
    """Wrapper class for convenient usage of the module-level search and browse agent"""

    def __init__(self, enable_js: bool = True, timeout: int = 30, debug: bool = False):
        self.context = SearchAndBrowseContext(timeout=timeout, debug=debug)

    async def run(self, instruction: str) -> Union[str, bool]:
        """
        Execute a search and browse task using the module-level agent.

        Args:
            instruction: Natural language instruction for the task

        Returns:
            Union[str, bool]: String for clarifications, True when complete
        """
        try:
            logger.info(f"🎯 Starting search and browse task: {instruction}")
            result = await agent.run(instruction, deps=self.context)
            logger.info("✅ Search and browse task completed")
            return result.output

        except Exception as e:
            import traceback

            error_msg = f"Search and browse task failed: {str(e)}"
            logger.error(f"❌ {error_msg}\nFull traceback:\n{traceback.format_exc()}")
            return error_msg


async def search_and_browse(
    instruction: str, timeout: int = 30, debug: bool = False
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
    agent = SearchAndBrowseAgent(timeout=timeout, debug=debug)
    return await agent.run(instruction)


# Export main functions and classes
__all__ = [
    "agent",  # Module-level agent for direct use
    "search_and_browse",
    "SearchAndBrowseAgent",
    "SearchAndBrowseTask",
    "SearchAndBrowseContext",
]
