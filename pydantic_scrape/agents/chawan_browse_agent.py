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
from typing import List, Type, TypeVar, Generic, Any, Union

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from pydantic_scrape.dependencies.chawan_browser_api import ChawanBrowser
from pydantic_scrape.toolsets.chawan_toolset import (
    ChawanContext,
    click_link_by_index,
    fill_form_bulk,
    fill_input,
    get_current_url,
    navigate_to,
    scroll_page,
    submit_form,
)


# Generic output type for typed browsing
T = TypeVar('T')

class ChawanBrowseTask(BaseModel, Generic[T]):
    """Task for interactive chawan browsing with dynamic output typing"""

    url: str
    objective: str = "Browse and extract information from the page"
    max_actions: int = 10
    timeout: int = 30
    # The magic happens here - specify what type you want back!
    output_type: Union[Type[T], Type[str]] = str  # Default to string for backward compatibility


# MODULE-LEVEL AGENT - Can be used directly or via wrapper class
# Simple agent with focused toolset
agent = Agent[str, ChawanContext](
    "openai:gpt-4o",
    deps_type=ChawanContext,
    tools=[
        navigate_to,          # Simple navigation with direct context mutation
        click_link_by_index,  # Click numbered links
        scroll_page,          # Scroll content
        fill_input,           # Fill single input fields
        fill_form_bulk,       # Fill multiple fields efficiently
        submit_form,          # Submit forms
        get_current_url,      # Get current URL
    ],
    system_prompt="""You are a focused web browsing agent following dependency-as-graph pattern.

All tools return simple ✅/❌ status messages and directly mutate the ChawanContext.
Your complete browsing state is tracked in the knowledge graph.
Use your memory to avoid repeating actions and build on previous discoveries.""",
)


@agent.instructions
def dynamic_chawan_instructions(ctx: RunContext[ChawanContext]) -> str:
    """Simple JSON dump of ChawanContext - let Pydantic structure do the work"""
    
    try:
        # Just dump the entire ChawanContext as JSON - the AI can figure it out
        return f"""Current browsing context:
        
{ctx.deps.render_state()}

Use the tools to accomplish your objective. All tools return simple status messages and update the context directly."""
    except Exception as e:
        logger.error(f"❌ Error serializing ChawanContext: {e}")
        return "Use the browsing tools to accomplish your objective."


class ChawanBrowseAgentV3:
    """Wrapper class for convenient usage with DYNAMIC OUTPUT TYPES! 🚀"""

    def __init__(self, enable_js: bool = True, debug: bool = False, timeout: int = 30):
        self.enable_js = enable_js
        self.debug = debug
        self.timeout = timeout

    async def browse_site(self, task: ChawanBrowseTask[T]) -> T:
        """Execute a browsing task using the module-level agent with toolset"""
        browser = None
        try:
            logger.info(f"🚀 Starting browse: {task.objective} -> {task.url}")

            # Initialize browser
            browser = ChawanBrowser(
                enable_js=self.enable_js, debug=self.debug, timeout=self.timeout
            )
            await browser.start()

            # Create context for the toolset - following new dependency-as-graph pattern
            context = ChawanContext(
                browser=browser,
                objective=task.objective,
                max_actions=task.max_actions
            )

            # DYNAMIC AGENT CONSTRUCTION BASED ON OUTPUT TYPE! 🚀
            if task.output_type != str:
                # Create typed agent dynamically!
                logger.info(f"🎯 Creating typed agent with output: {task.output_type.__name__}")
                
                # Build enhanced system prompt for structured output
                output_fields = ""
                if hasattr(task.output_type, 'model_fields'):
                    fields = list(task.output_type.model_fields.keys())
                    output_fields = f"\nRequired fields: {', '.join(fields)}"
                
                typed_agent = Agent(
                    "openai:gpt-4o",
                    deps_type=ChawanContext,
                    result_type=task.output_type,  # CRITICAL: This makes the agent return structured data!
                    tools=[
                        navigate_to, click_link_by_index, scroll_page, fill_input, submit_form,
                        get_current_url
                    ],
                    system_prompt=f"""
You are a web browsing agent that extracts information and returns it as structured data.

🎯 RETURN TYPE: You must return a {task.output_type.__name__} object with these fields:{output_fields}

IMPORTANT: 
- Do NOT return plain text, strings, or summaries
- Return ONLY the structured {task.output_type.__name__} object with all required fields filled
- Browse systematically using available tools
- Extract precise information to populate each field

The system expects a {task.output_type.__name__} object as output, not text.
"""
                )
                
                instruction = f"""
Accomplish this objective: {task.objective}

Starting URL: {task.url}
Maximum actions allowed: {task.max_actions}

🎯 RETURN FORMAT: {task.output_type.__name__} with structured data

Steps:
1. Navigate to the starting URL using navigate_to()
2. Analyze the page content and numbered links
3. Take appropriate actions to accomplish the objective  
4. Extract and return the information in the EXACT {task.output_type.__name__} format

Be methodical and extract structured data.
"""
                
                result = await typed_agent.run(instruction, deps=context)
                
            else:
                # Use original string-based agent for backward compatibility
                logger.info("📝 Using string-based agent (backward compatibility)")
                
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

            # Add comprehensive session summary using new ChawanContext structure
            summary = f"""

=== BROWSING SESSION SUMMARY ===
Objective: {task.objective}
Starting URL: {task.url}
Actions taken: {context.action_count}/{task.max_actions}
Pages visited: {len(context.pages)}
Successful actions: {context.successful_actions}
Final URL: {browser.get_current_url()}

Pages Visited:
""" + "\n".join(f"- {page.title} ({page.url})" for page in context.pages)

            if context.actions:
                summary += "\n\nAll Actions Taken:\n" + "\n".join(
                    f"- {action.action_type}: {action.target} ({action.status})" for action in context.actions
                )

            logger.info(f"✅ Completed browsing: {task.url}")
            
            # Return typed output or string with summary
            if task.output_type != str:
                # For typed output, return just the structured data
                logger.info(f"🎯 Returning typed output: {type(result.output)}")
                return result.output  # This is now type T!
            else:
                # For string output, include the summary
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
    tasks: List[ChawanBrowseTask[Any]],
    enable_js: bool = True, 
    debug: bool = False,
    timeout: int = 30,
    max_concurrent: int = 3,
) -> List[Any]:
    """
    🚀 REVOLUTIONARY: Parallel browsing with typed output support
    
    Execute multiple browsing tasks concurrently, each with their own specified output type!
    This is incredibly powerful for building structured data extraction pipelines.
    
    Args:
        tasks: List of ChawanBrowseTask objects, each can have different output types!
        enable_js: Enable JavaScript in browsers
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
        ChawanBrowseTask[NewsStory](
            url="https://news.com",
            output_type=NewsStory
        ),
        ChawanBrowseTask[Product](
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
