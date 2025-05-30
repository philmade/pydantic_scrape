"""
Basic AI scraping example - extract structured data using AI
"""

import asyncio
from typing import List, Tuple

from pydantic import BaseModel, Field

from pydantic_scrape.graphs.dynamic_scrape import scrape_with_ai


# Define what you want to extract
class NewsStories(BaseModel):
    stories: List[Tuple[str, str]] = Field(description="List of (title, url) pairs")


class BasicPageData(BaseModel):
    title: str = Field(description="Page title")
    headings: List[str] = Field(description="All h1, h2, h3 headings")
    links: List[str] = Field(description="All href links")


async def scrape_news():
    """Extract news stories from Hacker News"""
    print("=== Basic AI Scraping: Hacker News ===")

    result = await scrape_with_ai(
        url="https://news.ycombinator.com",
        output_type=NewsStories,
        extraction_prompt="Extract the top story titles and their URLs",
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"Successfully scraped {len(result['extracted_data']['stories'])} stories")
    print("\nTop 5 stories:")
    for i, (title, url) in enumerate(result["extracted_data"]["stories"][:5], 1):
        print(f"{i}. {title}")
        print(f"   {url}\n")


async def scrape_simple_page():
    """Extract basic data from a simple page"""
    print("=== Basic AI Scraping: Simple Page ===")

    result = await scrape_with_ai(
        url="https://example.com",
        output_type=BasicPageData,
        extraction_prompt="Extract the page title, all headings, and all links",
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    extracted = result["extracted_data"]
    print(f"Title: {extracted['title']}")
    print(f"Headings: {extracted['headings']}")
    print(f"Links: {extracted['links']}")


async def main():
    """Run all AI scraping examples"""
    print("🤖 Pydantic Scrape: AI Extraction Examples\n")

    # Simple page first
    await scrape_simple_page()
    print("\n" + "=" * 50 + "\n")

    # More complex page
    await scrape_news()

    print("✨ All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
