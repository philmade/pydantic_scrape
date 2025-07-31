from typing import Any, Dict, Optional, Type, Union

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, RunContext

# --- 1. Declarative Extraction Plan Models ---
# These models define the structure for the AI-generated extraction plan.


class FieldExtractor(BaseModel):
    """Instructions to extract a single data field."""

    selector: str = Field(..., description="The CSS selector to find the element.")
    attribute: Optional[str] = Field(
        default=None,
        description="The attribute to get (e.g., 'href', 'src'). If None, gets the text content.",
    )


class ListExtractor(BaseModel):
    """Instructions to extract a list of structured items."""

    container_selector: str = Field(
        ..., description="CSS selector for the parent element of each item in the list."
    )
    fields: Dict[str, FieldExtractor] = Field(
        ..., description="A mapping of item field names to their individual extractors."
    )


class ExtractionPlan(BaseModel):
    """The complete, declarative plan for extracting data for a target model."""

    plan: Dict[str, Union[FieldExtractor, ListExtractor]] = Field(
        ...,
        description="A mapping of target model fields to their extractor instructions.",
    )


# --- 2. Agent Context and Definition ---
# The context tracks state, and the agent generates the ExtractionPlan.


class ScrapeContext(BaseModel):
    """Context that tracks the scraping process."""

    soup: Any = Field(description="BeautifulSoup object", exclude=True)
    target_type: Type[BaseModel] = Field(
        description="Target Pydantic model type", exclude=True
    )
    schema_str: str = Field(
        description="String representation of the Pydantic model schema."
    )
    attempts: int = Field(default=0)
    last_plan: Optional[ExtractionPlan] = Field(default=None)
    last_error: str = Field(default="")
    success: bool = Field(default=False)


declarative_scrape_agent = Agent[ExtractionPlan, ScrapeContext](
    "openai:gpt-4o",
    output_type=ExtractionPlan,
    system_prompt="""You are an expert web scraping assistant. Your task is to analyze HTML and a target Pydantic schema, then generate a declarative JSON Extraction Plan using CSS selectors.

Your Goal: Create a valid `ExtractionPlan` JSON object that maps HTML elements to the fields in the target schema.

Workflow:
1.  Carefully examine the user's HTML and the `target_schema`.
2.  For each field in the schema, find the corresponding CSS selector in the HTML. For lists, find the selector for the container of each item, then the selectors for the fields inside each item.
3.  If you need an attribute like `href` or `src`, specify it in the `attribute` field. Otherwise, the text content will be extracted.
4.  Use the `test_extraction_plan` tool to validate your plan.
5.  If the tool reports an error (e.g., a selector returns nothing), analyze the error, correct your plan, and try again.
6.  You are finished when the `test_extraction_plan` tool returns a success message.
""",
)

# --- 3. Core Logic: Agent Tool and Plan Executor ---


def _execute_plan(
    soup: BeautifulSoup, plan: ExtractionPlan, target_model: Type[BaseModel]
) -> BaseModel:
    """Safely executes a declarative plan. Internal helper function."""
    extracted_data = {}
    for field_name, extractor in plan.plan.items():
        if isinstance(extractor, FieldExtractor):
            element = soup.select_one(extractor.selector)
            if element:
                value = (
                    element.get(extractor.attribute)
                    if extractor.attribute
                    else element.get_text(strip=True)
                )
                extracted_data[field_name] = value
        elif isinstance(extractor, ListExtractor):
            items_list = []
            for item_element in soup.select(extractor.container_selector):
                item_data = {}
                for item_field, item_extractor in extractor.fields.items():
                    child = item_element.select_one(item_extractor.selector)
                    if child:
                        item_data[item_field] = (
                            child.get(item_extractor.attribute)
                            if item_extractor.attribute
                            else child.get_text(strip=True)
                        )
                items_list.append(item_data)
            extracted_data[field_name] = items_list
    return target_model(**extracted_data)


@declarative_scrape_agent.tool
async def test_extraction_plan(
    ctx: RunContext[ScrapeContext], plan: ExtractionPlan
) -> str:
    """Executes and validates a declarative extraction plan against the HTML, providing feedback to the AI."""
    ctx.deps.attempts += 1
    ctx.deps.last_plan = plan
    logger.info(f"Attempt {ctx.deps.attempts}: Testing generated extraction plan...")

    try:
        # Execute the plan to see if it works and validates
        _execute_plan(ctx.deps.soup, plan, ctx.deps.target_type)
        ctx.deps.success = True
        logger.success(f"Extraction plan validated on attempt {ctx.deps.attempts}.")
        return "Success! The plan worked perfectly and the data was validated against the target model."

    except ValidationError as e:
        error_msg = f"Pydantic Validation Error: The extracted data does not match the schema. Details: {e}. Review your plan to ensure selectors target the correct data types."
        ctx.deps.last_error = error_msg
        return error_msg
    except Exception as e:
        error_msg = f"Runtime Error: The plan failed during execution. Details: '{e}'. One of your selectors is likely incorrect or missing. Please find the correct selector."
        ctx.deps.last_error = error_msg
        return error_msg


# --- 4. Public API Function ---


async def run_declarative_scraper(
    html_content: str,
    target_model: Type[BaseModel],
    extraction_prompt: str,
    max_attempts: int = 3,
) -> BaseModel:
    """
    Runs the declarative scraping agent to extract structured data from HTML.

    Args:
        html_content: The HTML source to scrape.
        target_model: The Pydantic model to populate.
        extraction_prompt: A natural language prompt describing what to extract.
        max_attempts: The maximum number of retries for the agent.

    Returns:
        A populated instance of the target_model.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    context = ScrapeContext(
        soup=soup,
        target_type=target_model,
        schema_str=str(target_model.model_json_schema()),
    )

    logger.info(f"🚀 Starting declarative scrape for {target_model.__name__}...")

    # The agent's goal is to produce a final, valid ExtractionPlan
    final_plan = await declarative_scrape_agent.run(
        f"HTML: ```html\n{html_content[:2500]}...\n```\n\n"
        f"Target Schema: ```json\n{context.schema_str}\n```\n\n"
        f"Task: {extraction_prompt}",
        deps=context,
        max_retries=max_attempts - 1,
    )

    if context.success and final_plan:
        logger.info("Final plan generated successfully. Executing it to get data...")
        return _execute_plan(soup, final_plan, target_model)
    else:
        logger.error(f"Extraction failed after {context.attempts} attempts.")
        raise ValueError(f"Failed to extract data. Last error: {context.last_error}")


# --- 5. Define Public Exports ---
__all__ = [
    "run_declarative_scraper",
    "declarative_scrape_agent",
    "FieldExtractor",
    "ListExtractor",
    "ExtractionPlan",
]
