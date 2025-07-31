"""
Agent Toolset

Tools for parallelizing and orchestrating other agents.
Provides clean separation of concerns for agent coordination.
"""

from typing import List

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import RunContext

from pydantic_scrape.agents.chawan_browse_agent import (
    ChawanBrowseTask,
    browse_sites_parallel,
)


class BrowseTasksRequest(BaseModel):
    """Request to browse multiple tasks in parallel"""
    tasks: List[ChawanBrowseTask]
    enable_js: bool = True
    debug: bool = False
    timeout: int = 30


async def browse_tasks_parallel(ctx: RunContext, request: BrowseTasksRequest) -> str:
    """
    Browse multiple websites in parallel using chawan browser automation.

    This tool orchestrates parallel browsing sessions with proper resource management.
    Each task gets its own browser instance for true parallelization.

    Args:
        ctx: Run context (standard pydantic-ai pattern)
        request: BrowseTasksRequest with tasks and configuration

    Returns:
        String with comprehensive browsing results from all sites
    """
    try:
        tasks = request.tasks
        logger.info(f"🚀 Starting parallel browse of {len(tasks)} sites")

        # Execute parallel browsing using the chawan_browse_agent function
        results = await browse_sites_parallel(
            tasks=tasks,
            enable_js=request.enable_js,
            debug=request.debug,
            timeout=request.timeout,
        )

        # Combine results with clean formatting
        combined_results = []
        for i, (task, result) in enumerate(zip(tasks, results, strict=False)):
            combined_results.append(f"""
=== SITE {i + 1}: {task.url} ===
Objective: {task.objective}
Max Actions: {task.max_actions}
Result:
{result}
{"=" * 50}
""")

        final_result = "\n".join(combined_results)
        logger.info(f"✅ Completed parallel browse of {len(tasks)} sites")
        return final_result

    except Exception as e:
        logger.error(f"❌ Parallel browse failed: {e}")
        return f"Failed to browse sites in parallel: {str(e)}"


# Export the agent coordination tools
__all__ = ["browse_tasks_parallel", "BrowseTasksRequest"]