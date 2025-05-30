"""
Simple Dynamic Scraper - AI agent with single function pattern
"""

import ast
from dataclasses import dataclass
from typing import Any, Optional, Type

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, RunContext


@dataclass
class SimpleScrapeContext:
    """Simple context for scraper"""

    current_soup: BeautifulSoup
    target_output_type: Type[BaseModel]
    extraction_attempts: list[str] = None
    last_result: Any = None
    last_error: Optional[str] = None

    def __post_init__(self):
        if self.extraction_attempts is None:
            self.extraction_attempts = []


# Tool and instruction functions defined separately
async def test_extraction_function(
    ctx: RunContext[SimpleScrapeContext], function_code: str
) -> str:
    """
    Test an extraction function against the current soup object.

    Args:
        function_code: Python function code to test

    Returns:
        Result message (success or error details)
    """
    try:
        # Validate Python syntax
        try:
            ast.parse(function_code)
        except SyntaxError as e:
            error_msg = f"Syntax Error: {e}"
            ctx.deps.last_error = error_msg
            return error_msg

        # Create execution environment
        exec_globals = {
            "soup": ctx.deps.current_soup,
            "output_type": ctx.deps.target_output_type,
            "__builtins__": __builtins__,
        }
        exec_locals = {}

        # Execute the function definition
        exec(function_code, exec_globals, exec_locals)

        # Check if extract_data function was defined
        if "extract_data" not in exec_locals:
            error_msg = "Error: Function must be named 'extract_data'"
            ctx.deps.last_error = error_msg
            return error_msg

        extract_func = exec_locals["extract_data"]

        # Call the function with soup and output_type
        result = extract_func(ctx.deps.current_soup, ctx.deps.target_output_type)

        # Validate the result is the correct type
        if not isinstance(result, ctx.deps.target_output_type):
            error_msg = f"Error: Function returned {type(result)}, expected {ctx.deps.target_output_type}"
            ctx.deps.last_error = error_msg
            return error_msg

        # Store successful result
        ctx.deps.last_result = result
        ctx.deps.last_error = None
        ctx.deps.extraction_attempts.append(function_code)

        # Show the full extracted data for review
        result_dict = result.model_dump()
        logger.info(f"Extraction function succeeded with {len(result_dict)} fields")

        # Format the result nicely for the AI to review
        formatted_result = "VALIDATION PASSED! Here's what your function extracted:\n\n"

        for field, value in result_dict.items():
            if isinstance(value, list):
                formatted_result += f"{field}: {len(value)} items\n"
                if len(value) > 0:
                    # Show first few items for review
                    for i, item in enumerate(value[:3]):
                        formatted_result += f"  {i + 1}. {item}\n"
                    if len(value) > 3:
                        formatted_result += f"  ... and {len(value) - 3} more\n"
                else:
                    formatted_result += "  (empty list - is this correct?)\n"
            elif isinstance(value, str):
                if value and value not in ["No title", "No URL", "", "N/A"]:
                    formatted_result += f"{field}: '{value}'\n"
                else:
                    formatted_result += f"{field}: '{value}' (seems empty/placeholder - is this correct?)\n"
            else:
                formatted_result += f"{field}: {value}\n"

        formatted_result += "\nREVIEW: Does this data look correct? If yes, return True. If not, improve your function."

        return formatted_result

    except ValidationError as e:
        error_msg = f"Validation Error: {e}"
        ctx.deps.last_error = error_msg
        return error_msg

    except Exception as e:
        error_msg = f"Runtime Error: {str(e)}"
        ctx.deps.last_error = error_msg
        return error_msg


async def show_current_state(ctx: RunContext[SimpleScrapeContext]) -> str:
    """Show the agent its current progress"""

    state_info = f"TARGET OUTPUT TYPE: {ctx.deps.target_output_type.__name__}\n"

    # MOST IMPORTANT: Show the actual HTML content
    if ctx.deps.current_soup:
        # Get the HTML string (limit length to avoid token overflow)
        html_content = str(ctx.deps.current_soup)
        if len(html_content) > 8000:  # Limit to ~8k chars
            html_content = html_content[:8000] + "\n... [HTML TRUNCATED] ..."

        state_info += f"\nHTML CONTENT TO ANALYZE:\n```html\n{html_content}\n```\n"
    else:
        state_info += "\nERROR: No HTML content available!\n"

    # Show the Pydantic schema
    if hasattr(ctx.deps.target_output_type, "model_json_schema"):
        schema = ctx.deps.target_output_type.model_json_schema()
        state_info += f"\nTARGET SCHEMA: {schema}\n"

    # Show attempts
    state_info += f"Attempts made: {len(ctx.deps.extraction_attempts)}\n"

    # Simple status
    if ctx.deps.last_error:
        state_info += "Last attempt failed. Try again.\n"
    elif ctx.deps.last_result:
        state_info += "Last function passed validation. Check the tool output to review extracted data.\n"
    else:
        state_info += "No attempts yet. Write your extract_data function.\n"

    return state_info


# Lazy initialization to avoid API key requirements at import time
_agent_instance = None


def get_bs4_scrape_script_agent():
    """Get the agent instance, creating it if needed"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = Agent(
            "gpt-4o",
            deps_type=SimpleScrapeContext,
            output_type=bool,  # Just returns True when successful
            instructions="""
You are a data extraction function generator. Write Python functions that extract structured data from HTML.

You have ONE tool: test_extraction_function

Your function must:
1. Be named 'extract_data'
2. Accept parameters: extract_data(soup, output_type) -> output_type  
3. Return a populated instance of output_type
4. Extract real data from the soup object

Keep calling test_extraction_function until you get correct data.
Return True only when the extracted data looks correct and complete.

Example function structure:
```python
def extract_data(soup, output_type):
    # Extract data from soup
    title = soup.find('h1').get_text(strip=True) if soup.find('h1') else None
    
    # Return populated output_type instance
    return output_type(title=title, ...)
```
            """.strip(),
        )

        # Register the tool and instructions
        _agent_instance.tool(test_extraction_function)
        _agent_instance.instructions(show_current_state)

    return _agent_instance


# For backward compatibility
bs4_scrape_script_agent = get_bs4_scrape_script_agent


async def extract_data_with_ai(
    soup: BeautifulSoup, output_type: Type[BaseModel], extraction_prompt: str
) -> BaseModel:
    """
    Use AI to extract data into the specified output type.

    Args:
        soup: BeautifulSoup object
        output_type: Pydantic model to extract into
        extraction_prompt: What to extract

    Returns:
        Populated output_type instance
    """
    context = SimpleScrapeContext(current_soup=soup, target_output_type=output_type)

    # Get the agent instance (this will create it if needed)
    agent = get_bs4_scrape_script_agent()

    # Run the agent
    result = await agent.run(extraction_prompt, deps=context)

    if result.output and context.last_result:
        return context.last_result
    else:
        raise ValueError(f"Extraction failed. Last error: {context.last_error}")


# Export
__all__ = [
    "bs4_scrape_script_agent",
    "extract_data_with_ai",
    "SimpleScrapeContext",
    "get_bs4_scrape_script_agent",
]
