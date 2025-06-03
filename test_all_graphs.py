#!/usr/bin/env python3
"""
Comprehensive Test Suite for All Pydantic Scrape Graphs

Tests all 4 main graph workflows with different content types to ensure
the framework works end-to-end for publication.

Graphs tested:
1. search_answer - Fast search → answer workflow
2. scrape_with_ai - Dynamic AI-powered scraping
3. execute_full_scrape_graph - Complete science scraping
4. optimized_search_scrape_answer - Search → scrape → answer with batch processing

Each test demonstrates a different use case and capability.
"""

import asyncio
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TestResult(BaseModel):
    """Standardized test result format"""

    graph_name: str = Field(description="Name of the graph tested")
    success: bool = Field(description="Whether the test passed")
    execution_time: float = Field(description="Time taken in seconds")
    result_summary: str = Field(description="Brief summary of results")
    error_message: str = Field(description="Error message if failed", default="")
    metadata: Dict[str, Any] = Field(
        description="Additional test metadata", default_factory=dict
    )


async def test_search_answer_graph() -> TestResult:
    """Test 1: Fast Search → Answer Workflow (Recommended for most users)"""
    print("🔍 Testing Search → Answer Graph...")

    try:
        from pydantic_scrape.graphs.search_answer import search_answer

        start_time = time.time()

        # Test with a research question
        result = await search_answer(
            query="Latest advances in quantum computing error correction",
            max_search_results=3,  # Keep small for fast testing
        )

        execution_time = time.time() - start_time

        if result.get("success"):
            answer_data = result["answer"]
            stats = result["processing_stats"]

            summary = f"Found {stats['search_results']} sources, generated comprehensive answer with {len(answer_data['key_insights'])} insights"

            return TestResult(
                graph_name="search_answer",
                success=True,
                execution_time=execution_time,
                result_summary=summary,
                metadata={
                    "sources_found": stats["search_results"],
                    "insights_count": len(answer_data["key_insights"]),
                    "answer_length": len(answer_data["answer"]),
                },
            )
        else:
            return TestResult(
                graph_name="search_answer",
                success=False,
                execution_time=execution_time,
                result_summary="Graph returned failure",
                error_message=result.get("error", "Unknown error"),
            )

    except Exception as e:
        return TestResult(
            graph_name="search_answer",
            success=False,
            execution_time=0,
            result_summary="Exception during execution",
            error_message=str(e),
        )


async def test_dynamic_scrape_graph() -> TestResult:
    """Test 2: Dynamic AI-Powered Scraping"""
    print("🤖 Testing Dynamic AI Scraping Graph...")

    try:
        from pydantic_scrape.graphs.dynamic_scrape import scrape_with_ai

        # Define what we want to extract
        class NewsData(BaseModel):
            headlines: List[str] = Field(description="Main news headlines")
            categories: List[str] = Field(description="News categories found")

        start_time = time.time()

        # Test with Hacker News (simple, reliable structure)
        result = await scrape_with_ai(
            url="https://news.ycombinator.com",
            output_type=NewsData,
            extraction_prompt="Extract the top headlines and identify main categories of news",
        )

        execution_time = time.time() - start_time

        # Check if we have an error or successful extraction
        if result.get("error"):
            return TestResult(
                graph_name="dynamic_scrape",
                success=False,
                execution_time=execution_time,
                result_summary="Scraping failed",
                error_message=result.get("error", "Unknown error"),
            )
        elif "extracted_data" in result:
            data = result["extracted_data"]
            summary = f"Extracted {len(data.get('headlines', []))} headlines and {len(data.get('categories', []))} categories"

            return TestResult(
                graph_name="dynamic_scrape",
                success=True,
                execution_time=execution_time,
                result_summary=summary,
                metadata={
                    "headlines_count": len(data.get("headlines", [])),
                    "categories_count": len(data.get("categories", [])),
                    "url_tested": "https://news.ycombinator.com",
                    "content_length": result.get("content_length", 0),
                },
            )
        else:
            return TestResult(
                graph_name="dynamic_scrape",
                success=False,
                execution_time=execution_time,
                result_summary="Unexpected result format",
                error_message="No extracted_data or error field found",
            )

    except Exception as e:
        return TestResult(
            graph_name="dynamic_scrape",
            success=False,
            execution_time=0,
            result_summary="Exception during execution",
            error_message=str(e),
        )


async def test_full_scrape_graph() -> TestResult:
    """Test 3: Complete Science Paper Scraping"""
    print("📄 Testing Complete Science Scraping Graph...")

    try:
        from pydantic_scrape.graphs.full_scrape_graph import execute_full_scrape_graph

        start_time = time.time()

        # Test with a well-known arXiv paper
        result = await execute_full_scrape_graph(
            url="https://arxiv.org/abs/2301.00001",  # Recent paper
            browser_config={"headless": True, "humanize": True},
        )

        execution_time = time.time() - start_time

        # Result is a FinalScrapeResult object, not a dict
        if result.success:
            content_type = result.content_type

            # Check for key indicators of successful science scraping
            has_metadata = bool(
                result.metadata.get("title") if result.metadata else False
            )
            has_content = len(result.full_text_content or "") > 100

            summary = f"Detected {content_type}, extracted {'metadata' if has_metadata else 'no metadata'}, {'full content' if has_content else 'minimal content'}"

            return TestResult(
                graph_name="full_scrape_graph",
                success=True,
                execution_time=execution_time,
                result_summary=summary,
                metadata={
                    "content_type": content_type,
                    "has_metadata": has_metadata,
                    "content_length": len(result.full_text_content or ""),
                    "confidence": result.confidence,
                },
            )
        else:
            return TestResult(
                graph_name="full_scrape_graph",
                success=False,
                execution_time=execution_time,
                result_summary="Scraping failed",
                error_message=result.get("error", "Unknown error"),
            )

    except Exception as e:
        return TestResult(
            graph_name="full_scrape_graph",
            success=False,
            execution_time=0,
            result_summary="Exception during execution",
            error_message=str(e),
        )


async def test_search_scrape_answer_graph() -> TestResult:
    """Test 4: Advanced Search → Scrape → Answer Pipeline"""
    print("🔬 Testing Search → Scrape → Answer Graph...")

    try:
        from pydantic_scrape.graphs.search_scrape_answer import (
            optimized_search_scrape_answer,
        )

        start_time = time.time()

        # Test with a scientific research question
        result = await optimized_search_scrape_answer(
            query="CRISPR gene editing safety concerns",
            max_results=2,  # Keep small for testing
            max_scrape_urls=2,  # Limit scraping for stability
        )

        execution_time = time.time() - start_time

        if result.get("success"):
            answer_data = result["answer"]
            stats = result.get("processing_stats", {})

            sources_found = stats.get("total_sources_found", 0)
            successful_scrapes = stats.get("successful_scrapes", 0)
            summaries_count = stats.get("summaries_generated", 0)

            summary = f"Found {sources_found} sources, scraped {successful_scrapes}, generated {summaries_count} summaries"

            return TestResult(
                graph_name="search_scrape_answer",
                success=True,
                execution_time=execution_time,
                result_summary=summary,
                metadata={
                    "sources_found": sources_found,
                    "successful_scrapes": successful_scrapes,
                    "summaries_generated": summaries_count,
                    "answer_confidence": answer_data.get("confidence", 0),
                },
            )
        else:
            return TestResult(
                graph_name="search_scrape_answer",
                success=False,
                execution_time=execution_time,
                result_summary="Pipeline failed",
                error_message=result.get("error", "Unknown error"),
            )

    except Exception as e:
        return TestResult(
            graph_name="search_scrape_answer",
            success=False,
            execution_time=0,
            result_summary="Exception during execution",
            error_message=str(e),
        )


async def run_all_tests() -> List[TestResult]:
    """Run all graph tests and return results"""

    print("🚀 Starting Comprehensive Graph Testing Suite")
    print("=" * 80)

    tests = [
        ("🔍 Search → Answer", test_search_answer_graph),
        ("🤖 Dynamic AI Scraping", test_dynamic_scrape_graph),
        ("📄 Complete Science Scraping", test_full_scrape_graph),
        ("🔬 Search → Scrape → Answer", test_search_scrape_answer_graph),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * 60)

        try:
            result = await test_func()
            results.append(result)

            if result.success:
                print(
                    f"✅ PASSED ({result.execution_time:.1f}s): {result.result_summary}"
                )
                if result.metadata:
                    for key, value in result.metadata.items():
                        print(f"   📊 {key}: {value}")
            else:
                print(
                    f"❌ FAILED ({result.execution_time:.1f}s): {result.result_summary}"
                )
                if result.error_message:
                    print(f"   🔴 Error: {result.error_message}")

        except Exception as e:
            print(f"💥 CRASHED: {str(e)}")
            results.append(
                TestResult(
                    graph_name=test_name,
                    success=False,
                    execution_time=0,
                    result_summary="Test crashed",
                    error_message=str(e),
                )
            )

    return results


async def generate_test_report(results: List[TestResult]) -> str:
    """Generate a markdown report of test results"""

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.success)
    total_time = sum(r.execution_time for r in results)

    report = f"""# Pydantic Scrape - Graph Test Results

**Test Summary:** {passed_tests}/{total_tests} graphs passing ✅  
**Total Execution Time:** {total_time:.1f} seconds  
**Test Date:** {time.strftime("%Y-%m-%d %H:%M:%S")}

## 📊 Results by Graph

"""

    for result in results:
        status_emoji = "✅" if result.success else "❌"
        report += f"""### {status_emoji} {result.graph_name.replace("_", " ").title()}

- **Status:** {"PASSED" if result.success else "FAILED"}
- **Execution Time:** {result.execution_time:.1f}s
- **Summary:** {result.result_summary}
"""

        if result.metadata:
            report += "- **Metrics:**\n"
            for key, value in result.metadata.items():
                report += f"  - {key.replace('_', ' ').title()}: {value}\n"

        if result.error_message and not result.success:
            report += f"- **Error:** {result.error_message}\n"

        report += "\n"

    # Add capability summary
    report += """## 🎯 Framework Capabilities Demonstrated

"""

    capabilities = {
        "search_answer": "🔍 **Fast Research** - Search academic sources and generate comprehensive answers in ~10 seconds",
        "dynamic_scrape": "🤖 **AI Extraction** - Dynamically extract structured data from any website using AI agents",
        "full_scrape_graph": "📄 **Science Processing** - Complete academic paper processing with metadata enrichment",
        "search_scrape_answer": "🔬 **Deep Research** - Advanced pipeline that searches, scrapes full content, and synthesizes answers",
    }

    for result in results:
        if result.success and result.graph_name in capabilities:
            report += f"- {capabilities[result.graph_name]}\n"

    if passed_tests == total_tests:
        report += f"\n🎉 **All {total_tests} core workflows are operational and ready for contributors!**"
    else:
        report += f"\n⚠️ **{total_tests - passed_tests} workflows need attention before publication.**"

    return report


async def main():
    """Run the comprehensive test suite"""

    results = await run_all_tests()

    print("\n" + "=" * 80)
    print("📋 FINAL TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for r in results if r.success)
    total = len(results)

    if passed == total:
        print(f"🎉 SUCCESS: All {total} graphs are working!")
    else:
        print(f"⚠️  PARTIAL: {passed}/{total} graphs working")

    # Generate and save test report
    report = await generate_test_report(results)

    with open("TEST_RESULTS.md", "w") as f:
        f.write(report)

    print("\n📄 Detailed test report saved to TEST_RESULTS.md")
    print(f"⏱️  Total test time: {sum(r.execution_time for r in results):.1f} seconds")

    return results


if __name__ == "__main__":
    asyncio.run(main())
