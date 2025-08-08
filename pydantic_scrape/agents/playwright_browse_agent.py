"""
Playwright Browse Agent v3 - Using Modular Toolset

Advanced web browsing agent using the modular playwright_toolset.
This provides clean separation between tools and agent logic.

Features:
- Uses modular playwright_toolset for all browser operations with anti-bot evasion
- Module-level agent for easy reuse and customization
- Memory-aware browsing with dynamic instructions
- Clean wrapper class for convenient usage
- WebKit engine with stealth techniques
"""

import asyncio
from typing import List, Type, TypeVar, Generic, Any, Union, cast

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from ..dependencies.playwright_webkit_api import PlaywrightWebKitBrowser
from ..toolsets.playwright_toolset import (
    PlaywrightContext,
    click_link_by_index,
    fill_form_bulk,
    fill_input,
    get_current_url,
    navigate_to,
    navigate_to_search,
    scroll_page,
    submit_form,
)
from gathersdk import AgentContext

# Generic output type for typed browsing
T = TypeVar("T")


class PlaywrightBrowseTask(BaseModel, Generic[T]):
    """Task for interactive chawan browsing with dynamic output typing"""

    url: str
    objective: str = "Browse and extract information from the page"
    # The magic happens here - specify what type you want back!
    output_type: Union[Type[T], Type[str]] = (
        str  # Default to string for backward compatibility
    )


async def browse_agent_factory(
    task: PlaywrightBrowseTask[T], agent_context: AgentContext
) -> T:
    """
    Execute a browsing task using the module-level agent with toolset.

    Args:
        task: The browsing task specifying URL, objective, and output type
        agent_context: AgentContext with conversation history and user info

    Returns:
        Result in the type specified by task.output_type (T)

    Note:
        If an error occurs, returns the error message cast to type T.
        This maintains type safety while handling the reality that errors are strings.
    """

    typed_agent = Agent(
        "openai:gpt-4o",
        deps_type=PlaywrightContext,
        output_type=task.output_type,  # CRITICAL: This makes the agent return structured data!
        tools=[
            # navigate_to,
            navigate_to_search,  # New search-filtered navigation
            click_link_by_index,
            scroll_page,
            fill_input,
            submit_form,
            fill_form_bulk,
            get_current_url,
        ],
        system_prompt=f"""
                        You are a web browsing agent that extracts information and returns it as structured data. You're in a public conversation and have been invoked to browse a site.
                        IMPORTANT: 
                        - Do NOT return plain text, strings, or summaries
                        - Return ONLY the structured {task.output_type.__name__} object with all required fields filled
                        - Browse systematically using available tools
                        - Extract precise information to populate each field

                        The system expects a {task.output_type.__name__} object as output, not text.
                        """,
    )

    @typed_agent.instructions
    def dynamic_playwright_instructions(ctx: RunContext[PlaywrightContext]) -> str:
        """Simple JSON dump of PlaywrightContext - let Pydantic structure do the work"""
        # Just dump the entire PlaywrightContext as JSON - the AI can figure it out
        return f""" {ctx.deps.agent_context.format_conversation_history(5)} Current browsing context:{ctx.deps.render_state()} Use the tools to accomplish your objective. All tools return simple status messages and update the context directly."""

    try:
        browser = None
        logger.info(f"🚀 Starting browse: {task.objective} -> {task.url}")
        # Initialize browser
        browser = PlaywrightWebKitBrowser(debug=False, timeout=10)
        await browser.start()
        result = await typed_agent.run(
            task.objective,
            deps=PlaywrightContext(
                url=task.url,
                agent_context=agent_context,
                browser=browser,
            ),
        )
        return result.output

    except Exception as e:
        import traceback

        error_msg = f"Failed browsing {task.url}: {str(e)}"
        full_traceback = traceback.format_exc()
        logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")

        # Return error message cast to the expected type
        # This is a limitation: errors are always strings, but we need to satisfy the type contract
        return cast(T, error_msg)

    finally:
        # Clean up browser session
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"⚠️ Browser cleanup failed: {e}")


async def markdown_browse_agent_factory(
    url: str, objective: str, agent_context: AgentContext
) -> str:
    """
    Simple string-based browse factory for basic agents.

    This is a simpler alternative to the typed browse_agent_factory that always
    returns a string summary of the browsing session. Perfect for basic agents
    that just need to browse and report information.

    Args:
        url: URL to browse
        objective: What you want to accomplish
        agent_context: AgentContext with conversation history and user info

    Returns:
        str: Summary of the browsing session results

    Example:
        result = await simple_browse_agent_factory(
            "https://example.com",
            "Find the pricing information",
            agent_context
        )
    """

    # Create a simple agent focused on returning text summaries
    simple_agent = Agent(
        "openai:gpt-4o",
        deps_type=PlaywrightContext,
        output_type=str,  # Always returns string
        tools=[
            navigate_to,
            navigate_to_search,  # New search-filtered navigation
            click_link_by_index,
            scroll_page,
            fill_input,
            submit_form,
            fill_form_bulk,
            get_current_url,
        ],
        system_prompt="""You are a web browsing agent that extracts information and returns clear text summaries.
        
        Your task:
        1. Navigate to the specified URL
        2. Use available tools to browse and find information
        3. Return a clear, concise summary of what you found
        
        Focus on being helpful and extracting the key information requested.
        Return your findings as a well-formatted text summary in markdown format""",
    )

    @simple_agent.instructions
    def dynamic_browse_instructions(ctx: RunContext[PlaywrightContext]) -> str:
        """Provide browsing context and history"""
        conversation = (
            ctx.deps.agent_context.format_conversation_history(5)
            if ctx.deps.agent_context
            else ""
        )
        return f"""{conversation}

Current browsing state: {ctx.deps.render_state()}

Use the tools to accomplish the objective: {objective}
Navigate systematically and extract the requested information."""

    try:
        browser = None
        logger.info(f"🌐 Simple browse starting: {objective} -> {url}")

        # Initialize browser
        browser = PlaywrightWebKitBrowser(debug=False, timeout=10)
        await browser.start()

        # Run the agent
        result = await simple_agent.run(
            objective,
            deps=PlaywrightContext(
                url=url,
                objective=objective,
                agent_context=agent_context,
                browser=browser,
            ),
        )

        logger.info(f"✅ Simple browse completed")
        return result.output

    except Exception as e:
        import traceback

        error_msg = f"Browse failed for {url}: {str(e)}"
        full_traceback = traceback.format_exc()
        logger.error(f"❌ {error_msg}\nTraceback:\n{full_traceback}")
        return f"❌ {error_msg}"

    finally:
        # Clean up browser
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"⚠️ Browser cleanup failed: {e}")


# Convenience functions for easy usage
async def browse_site_interactive(
    agent_context: AgentContext,
    url: str,
    objective: str = "Browse and extract information from the page",
) -> str:
    """
    Browse a site interactively using the browse_agent_factory.

    Args:
        url: URL to browse
        objective: What you want to accomplish
        agent_context: Optional AgentContext for conversation history

    Returns:
        Results of the browsing session
    """
    task = PlaywrightBrowseTask[str](url=url, objective=objective, output_type=str)

    # Use a minimal AgentContext if none provided
    if agent_context is None:
        from gathersdk import AgentContext

        agent_context = AgentContext(user_id="test", chat_id="test")

    return await browse_agent_factory(task, agent_context)


async def browse_sites_parallel(
    tasks: List[PlaywrightBrowseTask[Any]],
    agent_context: AgentContext,
) -> List[Any]:
    """
    🚀 REVOLUTIONARY: Parallel browsing with typed output support

    Execute multiple browsing tasks concurrently, each with their own specified output type!
    This is incredibly powerful for building structured data extraction pipelines.

    Args:
        tasks: List of PlaywrightBrowseTask objects, each can have different output types!
        debug: Enable detailed logging
        timeout: Default timeout for browser operations
        max_concurrent: Maximum number of concurrent browsing sessions

    Returns:
        List[Any]: List of results, each in the type specified by the corresponding task

        Note: Due to Python typing limitations with heterogeneous lists, return type
        is List[Any], but each element will be the exact type specified in the task.

    Example:
    ```python
    class NewsStory(BaseModel):
        title: str
        summary: str

    class Product(BaseModel):
        name: str
        price: str

    tasks = [
        PlaywrightBrowseTask[NewsStory](
            url="https://news.com",
            output_type=NewsStory
        ),
        PlaywrightBrowseTask[Product](
            url="https://shop.com/item",
            output_type=Product
        )
    ]

    results = await browse_sites_parallel(tasks)
    # results[0] is NewsStory, results[1] is Product!
    ```

    Benefits:
        🚀 Concurrent execution for faster data extraction
        🎯 Each task can have different output types
        📊 Build complex structured data pipelines
        ⚡ Efficient resource usage with controlled concurrency

    Old Args:
        tasks: List of PlaywrightBrowseTask objects to execute
        debug: Enable debug logging
        timeout: Default timeout for browser operations

    Returns:
        List of browsing results, one per task (in same order)
    """
    logger.info(f"🚀 Starting parallel browsing of {len(tasks)} sites")

    async def browse_single_task(
        task: PlaywrightBrowseTask, task_id: int, agent_context: AgentContext
    ) -> str:
        """Browse a single task with error handling"""
        try:
            logger.info(f"[Task {task_id}] Starting browse: {task.url}")

            result = await browse_agent_factory(task, agent_context)
            logger.info(f"[Task {task_id}] ✅ Completed: {task.url}")
            return result

        except Exception as e:
            error_msg = f"[Task {task_id}] ❌ Failed to browse {task.url}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    # Execute all tasks in parallel
    results = await asyncio.gather(
        *[browse_single_task(task, i, agent_context) for i, task in enumerate(tasks)],
        return_exceptions=True,
    )

    # Convert any exceptions to error strings
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            error_msg = f"[Task {i}] Exception: {str(result)}"
            logger.error(error_msg)
            processed_results.append(error_msg)
        else:
            processed_results.append(result)

    logger.info(f"✅ Completed parallel browsing of {len(tasks)} sites")
    return processed_results


# Export main functions and classes
__all__ = [
    "browse_agent_factory",  # Main typed factory function
    "simple_browse_agent_factory",  # Simple string-based factory
    "browse_site_interactive",
    "browse_sites_parallel",
    "PlaywrightBrowseTask",
]
