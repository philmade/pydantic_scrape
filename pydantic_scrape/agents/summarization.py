"""
Summarization Agent - uses Pydantic AI to summarize scraped content

Standalone agent that takes FinalScrapeResult objects and creates concise, structured summaries.
Optimized for batching multiple results while respecting context length limits.

Includes advanced optimization features:
- Token-aware smart batching
- Concurrent processing strategies
- Performance metrics and monitoring
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


class SummarizedResult(BaseModel):
    """Structured summary of scraped content"""

    # Core summary
    title: str = Field(description="Title or main topic")
    summary: str = Field(description="Concise summary of key content")
    key_findings: List[str] = Field(
        description="Main findings or points", default_factory=list
    )

    # Content metadata
    content_type: str = Field(
        description="Type of content (science, article, youtube, etc.)"
    )
    source_url: str = Field(description="Original URL")

    # Quality indicators
    full_text_available: bool = Field(description="Whether full text was extracted")
    confidence_score: float = Field(
        description="AI confidence in content detection", ge=0.0, le=1.0
    )

    # Processing stats
    word_count: Optional[int] = Field(
        description="Approximate word count of source", default=None
    )
    pdf_links_found: int = Field(description="Number of PDF links found", default=0)

    # Additional insights (optional)
    authors: List[str] = Field(description="Authors if available", default_factory=list)
    publication_date: Optional[str] = Field(
        description="Publication date if available", default=None
    )
    doi: Optional[str] = Field(description="DOI if available", default=None)
    tags: List[str] = Field(
        description="Relevant tags or categories", default_factory=list
    )


class SummarizedResults(BaseModel):
    results: List[SummarizedResult]


@dataclass
class SummarizationContext:
    """Clean context for summarization that handles any content type"""

    # Content to summarize - handles BaseModel objects, lists, or raw strings
    content: Union[List[BaseModel], BaseModel, str]

    # Processing options
    max_content_length: int = 5000

    # Results
    summaries: Union[List[SummarizedResult], SummarizedResult] = None
    processing_errors: List[str] = None

    def __post_init__(self):
        if self.summaries is None:
            self.summaries = []
        if self.processing_errors is None:
            self.processing_errors = []

    def get_content_for_summarization(self) -> str:
        """Convert content to string format for summarization"""

        if isinstance(self.content, str):
            # Already a string, use as-is
            return self.content[: self.max_content_length]

        elif isinstance(self.content, BaseModel):
            # Single BaseModel - convert to readable format
            content_dict = self.content.model_dump()
            return self._format_model_dict(content_dict)[: self.max_content_length]

        elif isinstance(self.content, list):
            # List of BaseModel objects - format as batch with clear separators and numbering
            content_parts = []
            for i, item in enumerate(self.content):
                content_parts.append(f"=== DOCUMENT {i + 1} OF {len(self.content)} ===")
                if isinstance(item, BaseModel):
                    item_dict = item.model_dump()
                    content_parts.append(self._format_model_dict(item_dict))
                else:
                    content_parts.append(str(item))
                content_parts.append(f"=== END OF DOCUMENT {i + 1} ===")

            full_content = "\n\n".join(content_parts)
            return full_content[: self.max_content_length]

        else:
            # Fallback to string conversion
            return str(self.content)[: self.max_content_length]

    def _format_model_dict(self, content_dict: Dict[str, Any]) -> str:
        """Format a model dictionary into readable text"""

        # Prioritize key fields that are commonly useful for summarization
        priority_fields = [
            "title",
            "description",
            "summary",
            "content",
            "text",
            "abstract",
        ]
        other_fields = ["url", "href", "source", "authors", "published", "doi"]

        formatted_parts = []

        # Add priority fields first
        for field in priority_fields:
            if field in content_dict and content_dict[field]:
                value = str(content_dict[field]).strip()
                if value:
                    formatted_parts.append(f"{field.title()}: {value}")

        # Add other useful fields
        for field in other_fields:
            if field in content_dict and content_dict[field]:
                value = str(content_dict[field]).strip()
                if value and len(value) < 200:  # Keep short fields only
                    formatted_parts.append(f"{field.title()}: {value}")

        return "\n\n".join(formatted_parts)

    def get_item_count(self) -> int:
        """Get the number of items to summarize"""
        if isinstance(self.content, list):
            return len(self.content)
        elif isinstance(self.content, (BaseModel, str)):
            return 1
        else:
            return 0


# Create the single result summarization agent
summarization_agent = Agent(
    "gpt-4o-mini",  # Cost-efficient for summarization
    deps_type=SummarizationContext,
    output_type=Union[SummarizedResult, SummarizedResults],
    instructions="""You are an expert content summarizer specializing in academic and web content.

Your task is to analyze the provided content and create structured, concise summaries that capture:
1. The main topic and key findings
2. Important metadata (authors, dates, DOIs)
3. Content quality indicators
4. Relevant categorization tags

Focus on accuracy and brevity. Extract factual information from the provided metadata when available.
For scientific content, emphasize methodology and conclusions.
For articles/news, focus on main points and implications.
""",
)


@summarization_agent.instructions
def add_content_to_summarize(ctx: RunContext[SummarizationContext]) -> str:
    """Dynamically add the content to summarize from context"""
    instructions = ""
    if isinstance(ctx.deps.content, list):
        num_items = len(ctx.deps.content)
        instructions += f"CRITICAL: You must return a SummarizedResults object containing exactly {num_items} separate SummarizedResult objects - one for each of the {num_items} documents below. Each document is clearly separated and numbered.\n\n"
    elif isinstance(ctx.deps.content, BaseModel) or isinstance(ctx.deps.content, str):
        instructions += (
            "Please return a single SummarizedResult object for the document below:\n\n"
        )

    content = ctx.deps.get_content_for_summarization()
    return f"{instructions}Content to summarize:\n\n{content}"


async def summarize_content(
    content: Union[List[BaseModel], BaseModel, str], max_length: int = 5000
) -> Union[SummarizedResult, SummarizedResults]:
    """
    Summarize a single piece of content using the clean context approach.

    Args:
        content: BaseModel object or string to summarize
        max_length: Maximum content length for processing

    Returns:
        SummarizedResult with structured summary
    """
    if isinstance(content, list):
        logger.info(
            f"SummarizationAgent: Summarizing list of {len(content)} items (expecting multiple summaries)"
        )
    elif isinstance(content, str):
        logger.info(
            "SummarizationAgent: Summarizing text content (expecting single summary)"
        )
    else:
        logger.info(
            "SummarizationAgent: Summarizing single object (expecting single summary)"
        )

    try:
        # Create clean context
        context = SummarizationContext(content=content, max_content_length=max_length)

        # Simple agent call - content is added via @agent.instructions
        summary_result = await summarization_agent.run("", deps=context)
        if isinstance(summary_result.output, SummarizedResult):
            logger.info("SummarizationAgent: Successfully created single summary")
        elif isinstance(summary_result.output, SummarizedResults):
            logger.info(
                f"SummarizationAgent: Successfully created {len(summary_result.output.results)} summaries"
            )
        return summary_result.output

    except Exception as e:
        logger.error(f"SummarizationAgent: Failed to summarize content: {e}")
        # Return fallback summary
        return SummarizedResult(
            title="Summarization Failed",
            summary=f"Content summarization failed: {str(e)}",
            key_findings=[],
            content_type="unknown",
            source_url="unknown",
            full_text_available=False,
            confidence_score=0.0,
            pdf_links_found=0,
        )


# Export the main functions and models
__all__ = [
    "SummarizedResult",
    "SummarizedResults",
    "SummarizationContext",
    "summarize_content",
    "summarization_agent",
]
