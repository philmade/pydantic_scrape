"""
Science content detection and extraction examples
"""

import asyncio
from typing import List, Optional

from pydantic import BaseModel, Field

from pydantic_scrape.graphs.dynamic_scrape import scrape_with_ai


# Models for different types of scientific content
class SciencePaper(BaseModel):
    title: str = Field(description="Paper title")
    authors: List[str] = Field(description="List of author names")
    abstract: str = Field(description="Paper abstract")
    doi: Optional[str] = Field(description="DOI if available")
    publication_date: Optional[str] = Field(description="Publication date")


class BlogPost(BaseModel):
    title: str = Field(description="Blog post title")
    author: Optional[str] = Field(description="Author name if available")
    content_summary: str = Field(description="Brief summary of the content")
    tags: List[str] = Field(description="Topic tags or categories")


class NewsArticle(BaseModel):
    headline: str = Field(description="News headline")
    summary: str = Field(description="Article summary")
    publication: Optional[str] = Field(description="News publication name")
    date: Optional[str] = Field(description="Publication date")


async def detect_science_paper():
    """Detect and extract data from a scientific paper"""
    print("=== Science Paper Detection ===")

    # Try ArXiv paper
    result = await scrape_with_ai(
        url="https://arxiv.org/abs/2301.00001",
        output_type=SciencePaper,
        extraction_prompt="Extract scientific paper metadata including title, authors, abstract, and DOI",
    )

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    paper = result["extracted_data"]
    print("✅ Detected Science Paper:")
    print(f"   Title: {paper['title']}")
    print(
        f"   Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}"
    )
    print(f"   DOI: {paper['doi'] or 'Not found'}")
    print(f"   Abstract: {paper['abstract'][:150]}...")


async def detect_blog_content():
    """Detect and extract data from a blog post"""
    print("\n=== Blog Content Detection ===")

    # Try a tech blog
    result = await scrape_with_ai(
        url="https://blog.python.org/",
        output_type=BlogPost,
        extraction_prompt="Extract blog post information including title, author, content summary, and tags",
    )

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    blog = result["extracted_data"]
    print("✅ Detected Blog Content:")
    print(f"   Title: {blog['title']}")
    print(f"   Author: {blog['author'] or 'Not specified'}")
    print(f"   Summary: {blog['content_summary'][:150]}...")
    print(f"   Tags: {', '.join(blog['tags']) if blog['tags'] else 'None found'}")


async def detect_news_content():
    """Detect and extract data from news content"""
    print("\n=== News Content Detection ===")

    # Try Hacker News (tech news aggregator)
    class NewsHeadlines(BaseModel):
        top_stories: List[str] = Field(description="List of top story headlines")

    result = await scrape_with_ai(
        url="https://news.ycombinator.com",
        output_type=NewsHeadlines,
        extraction_prompt="Extract the top news story headlines from the page",
    )

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    news = result["extracted_data"]
    print("✅ Detected News Content:")
    print(f"   Found {len(news['top_stories'])} headlines")
    print("   Top 3 stories:")
    for i, headline in enumerate(news["top_stories"][:3], 1):
        print(f"   {i}. {headline[:100]}...")


async def adaptive_content_detection():
    """Demonstrate adaptive content detection based on URL patterns"""
    print("\n=== Adaptive Content Detection ===")

    test_urls = [
        ("https://example.com", "Generic webpage"),
        ("https://arxiv.org/abs/2301.00001", "Scientific paper"),
        ("https://news.ycombinator.com", "News aggregator"),
    ]

    # Generic model that works for any content type
    class GenericContent(BaseModel):
        title: str = Field(description="Page title")
        content_type: str = Field(
            description="Type of content (blog, news, academic, etc.)"
        )
        main_points: List[str] = Field(
            description="Key points or topics from the content"
        )

    for url, description in test_urls:
        print(f"\nTesting {description}: {url}")

        result = await scrape_with_ai(
            url=url,
            output_type=GenericContent,
            extraction_prompt="Analyze this page and extract the title, determine content type, and list main points",
        )

        if "error" in result:
            print(f"   ❌ Error: {result['error']}")
            continue

        content = result["extracted_data"]
        print(f"   ✅ Title: {content['title']}")
        print(f"   📝 Type: {content['content_type']}")
        print(f"   🔑 Points: {', '.join(content['main_points'][:2])}...")


async def main():
    """Run all content detection examples"""
    print("🔍 Pydantic Scrape: Content Type Detection Examples\n")

    await detect_science_paper()
    await detect_blog_content()
    await detect_news_content()
    await adaptive_content_detection()

    print("\n✨ All detection examples completed!")
    print("\n📖 Key insights:")
    print("   • AI automatically adapts to different content types")
    print("   • Structured models ensure consistent data extraction")
    print("   • Same framework works across diverse content sources")
    print("   • Error handling maintains robust operation")


if __name__ == "__main__":
    asyncio.run(main())
