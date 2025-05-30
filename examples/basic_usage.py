"""
Complete usage example showing the full Pydantic Scrape workflow
"""

import asyncio
from typing import List, Tuple

from pydantic import BaseModel, Field

from pydantic_scrape.dependencies import FetchDependency
from pydantic_scrape.graphs.dynamic_scrape import scrape_with_ai


# Define extraction models
class ProductInfo(BaseModel):
    name: str = Field(description="Product name")
    price: str = Field(description="Product price")
    description: str = Field(description="Product description")


class NewsHeadlines(BaseModel):
    headlines: List[Tuple[str, str]] = Field(
        description="List of (headline, url) pairs"
    )


async def example_dependency_usage():
    """Example: Using dependencies directly"""
    print("=== Direct Dependency Usage ===")

    # Use the fetch dependency directly
    fetch_dep = FetchDependency(timeout_ms=30000)

    result = await fetch_dep.fetch_content(
        "https://httpbin.org/html", browser_config={"headless": True, "humanize": True}
    )

    if result.error:
        print(f"❌ Fetch failed: {result.error}")
        return

    print(f"✅ Successfully fetched: {result.title}")
    print(f"   Content: {len(result.content)} characters")
    print(f"   Duration: {result.fetch_duration:.2f}s")


async def example_ai_extraction():
    """Example: AI-powered data extraction"""
    print("\n=== AI-Powered Extraction ===")

    # Define what we want to extract
    class SimpleData(BaseModel):
        title: str = Field(description="Page title")
        main_content: str = Field(description="Main text content")

    result = await scrape_with_ai(
        url="https://example.com",
        output_type=SimpleData,
        extraction_prompt="Extract the page title and main content text",
    )

    if "error" in result:
        print(f"❌ AI extraction failed: {result['error']}")
        return

    extracted = result["extracted_data"]
    print("✅ AI extracted data:")
    print(f"   Title: {extracted['title']}")
    print(f"   Content: {extracted['main_content'][:100]}...")


async def example_complex_extraction():
    """Example: Complex structured data extraction"""
    print("\n=== Complex Data Extraction ===")

    result = await scrape_with_ai(
        url="https://news.ycombinator.com",
        output_type=NewsHeadlines,
        extraction_prompt="Extract news headlines and their URLs from the page",
    )

    if "error" in result:
        print(f"❌ Complex extraction failed: {result['error']}")
        return

    headlines = result["extracted_data"]["headlines"]
    print(f"✅ Extracted {len(headlines)} headlines:")

    # Show first 3 headlines
    for i, (headline, url) in enumerate(headlines[:3], 1):
        print(f"   {i}. {headline}")
        print(f"      → {url}")


async def example_error_handling():
    """Example: Proper error handling"""
    print("\n=== Error Handling Example ===")

    # Try to fetch a non-existent page
    result = await scrape_with_ai(
        url="https://httpbin.org/status/404",
        output_type=SimpleData,
        extraction_prompt="Extract any data from this page",
    )

    if "error" in result:
        print(f"✅ Properly handled error: {result['error']}")
    else:
        print("❌ Expected an error but didn't get one")


class SimpleData(BaseModel):
    title: str = Field(description="Page title")
    content: str = Field(description="Main content")


async def main():
    """Run all usage examples"""
    print("🚀 Pydantic Scrape: Complete Usage Examples\n")

    await example_dependency_usage()
    await example_ai_extraction()
    await example_complex_extraction()
    await example_error_handling()

    print("\n✨ All usage examples completed!")
    print("\n📖 Key takeaways:")
    print("   • Dependencies handle the heavy lifting")
    print("   • AI extraction uses structured Pydantic models")
    print("   • Error handling is built-in and consistent")
    print("   • Type safety throughout the entire pipeline")


if __name__ == "__main__":
    asyncio.run(main())
