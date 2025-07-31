"""
Chawan Browse Agent v3 - Using Modular Toolset

Advanced web browsing agent using the modular chawan_toolset.
This provides clean separation between tools and agent logic.

Features:
- Uses modular chawan_toolset for all browser operations
- Module-level agent for easy reuse and customization
- Memory-aware browsing with dynamic instructions
- Clean wrapper class for convenient usage
"""

import asyncio
from typing import List

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent

from pydantic_scrape.dependencies.chawan_browser_api import ChawanBrowser
from pydantic_scrape.toolsets.chawan_toolset import (
    ChawanContext,
    click_link_by_index,
    create_chawan_instructions,
    detect_form_fields,
    # Enhanced form tools (based on agent feedback)
    fill_form_bulk,
    # Basic form tools
    get_current_url,
    get_form_snapshot,
    navigate_to_with_search,
    scroll_page,
    submit_form,
)


class ChawanBrowseTask(BaseModel):
    """Task for interactive chawan browsing"""

    url: str
    objective: str = "Browse and extract information from the page"
    max_actions: int = 10
    timeout: int = 30


# MODULE-LEVEL AGENT - Can be used directly or via wrapper class
# Simple agent with focused toolset
agent = Agent[str, ChawanContext](
    "openai:gpt-4o",
    deps_type=ChawanContext,
    tools=[
        navigate_to_with_search,  # Smart navigation with auto cookie dismissal
        click_link_by_index,
        scroll_page,
        detect_form_fields,
        fill_form_bulk,  # Bulk form filling
        get_form_snapshot,
        submit_form,
        get_current_url,
    ],
    system_prompt="""You are a focused web browsing agent with essential tools.

Use navigate_to_with_search() with search terms when looking for specific content.
Cookie popups are automatically dismissed during navigation.
Use fill_form_bulk() for efficient form filling.
Always get_form_snapshot() before submit_form().""",
)


@agent.instructions
def instructions(ctx):
    return create_chawan_instructions(ctx)


class ChawanBrowseAgentV3:
    """Wrapper class for convenient usage of the module-level chawan agent"""

    def __init__(self, enable_js: bool = True, debug: bool = False, timeout: int = 30):
        self.enable_js = enable_js
        self.debug = debug
        self.timeout = timeout

    async def browse_site(self, task: ChawanBrowseTask) -> str:
        """Execute a browsing task using the module-level agent with toolset"""
        browser = None
        try:
            logger.info(f"🚀 Starting browse: {task.objective} -> {task.url}")

            # Initialize browser
            browser = ChawanBrowser(
                enable_js=self.enable_js, debug=self.debug, timeout=self.timeout
            )
            await browser.start()

            # Create context for the toolset
            context = ChawanContext(
                browser=browser,
                objective=task.objective,
                max_actions=task.max_actions,
                visited_urls=[],
                clicked_links=[],
                actions_taken=[],
                pages_browsed=set(),
            )

            # Execute browsing task using module-level agent
            instruction = f"""
Accomplish this objective: {task.objective}

Starting URL: {task.url}
Maximum actions allowed: {task.max_actions}

Steps to follow:
1. Navigate to the starting URL
2. Analyze the page content and structure
3. Take appropriate actions to accomplish the objective
4. Extract and return relevant information

Be methodical and describe what you see at each step.
"""

            result = await agent.run(instruction, deps=context)

            # Add comprehensive session summary
            summary = f"""

=== BROWSING SESSION SUMMARY ===
Objective: {task.objective}
Starting URL: {task.url}
Actions taken: {context.action_count}/{task.max_actions}
URLs visited: {len(context.visited_urls)}
Links clicked: {len(context.clicked_links)}
Pages browsed: {len(context.pages_browsed)}
Final URL: {browser.get_current_url()}

Visited URLs:
""" + "\n".join(f"- {url}" for url in context.visited_urls)

            if context.clicked_links:
                summary += "\n\nClicked Links:\n" + "\n".join(
                    f"- {link}" for link in context.clicked_links
                )

            if context.actions_taken:
                summary += "\n\nAll Actions Taken:\n" + "\n".join(
                    f"- {action}" for action in context.actions_taken
                )

            logger.info(f"✅ Completed browsing: {task.url}")
            return str(result.output) + summary

        except Exception as e:
            import traceback

            error_msg = f"Failed browsing {task.url}: {str(e)}"
            full_traceback = traceback.format_exc()
            logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")
            return f"{error_msg}\nTraceback: {full_traceback}"

        finally:
            # Clean up browser session
            if browser:
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning(f"⚠️ Browser cleanup failed: {e}")


# Convenience functions for easy usage
async def browse_site_interactive(
    url: str,
    objective: str = "Browse and extract information from the page",
    max_actions: int = 10,
    timeout: int = 30,
    enable_js: bool = True,
    debug: bool = False,
) -> str:
    """
    Browse a site interactively using the module-level agent with toolset.

    Args:
        url: URL to browse
        objective: What you want to accomplish
        max_actions: Maximum number of actions to take
        timeout: Timeout for browser operations
        enable_js: Enable JavaScript execution
        debug: Enable debug logging

    Returns:
        Results of the browsing session
    """
    task = ChawanBrowseTask(
        url=url, objective=objective, max_actions=max_actions, timeout=timeout
    )

    agent_wrapper = ChawanBrowseAgentV3(
        enable_js=enable_js, debug=debug, timeout=timeout
    )
    return await agent_wrapper.browse_site(task)


async def browse_sites_parallel(
    tasks: List[ChawanBrowseTask],
    enable_js: bool = True,
    debug: bool = False,
    timeout: int = 30,
) -> List[str]:
    """
    Browse multiple sites in parallel using the module-level agent.

    Args:
        tasks: List of ChawanBrowseTask objects to execute
        enable_js: Enable JavaScript execution for all browsers
        debug: Enable debug logging
        timeout: Default timeout for browser operations

    Returns:
        List of browsing results, one per task (in same order)
    """
    logger.info(f"🚀 Starting parallel browsing of {len(tasks)} sites")

    async def browse_single_task(task: ChawanBrowseTask, task_id: int) -> str:
        """Browse a single task with error handling"""
        try:
            logger.info(f"[Task {task_id}] Starting browse: {task.url}")

            agent_wrapper = ChawanBrowseAgentV3(
                enable_js=enable_js, debug=debug, timeout=task.timeout or timeout
            )

            result = await agent_wrapper.browse_site(task)
            logger.info(f"[Task {task_id}] ✅ Completed: {task.url}")
            return result

        except Exception as e:
            error_msg = f"[Task {task_id}] ❌ Failed to browse {task.url}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    # Execute all tasks in parallel
    results = await asyncio.gather(
        *[browse_single_task(task, i) for i, task in enumerate(tasks)],
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
    "agent",  # Module-level agent for direct use
    "browse_site_interactive",
    "browse_sites_parallel",
    "ChawanBrowseTask",
    "ChawanBrowseAgentV3",
]
