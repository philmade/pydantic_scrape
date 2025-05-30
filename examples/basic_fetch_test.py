"""
Basic fetch dependency test - testing just the fetch functionality
"""

import asyncio

from pydantic_scrape.dependencies.fetch import FetchDependency


async def test_basic_fetch():
    """Test the basic fetch functionality"""
    print("=== Testing Basic Fetch Functionality ===")

    fetch_dep = FetchDependency(timeout_ms=30000)

    # Test with a simple, reliable URL
    result = await fetch_dep.fetch_content(
        "https://httpbin.org/html", browser_config={"headless": True, "humanize": True}
    )

    if result.error:
        print(f"❌ Error: {result.error}")
        return False

    print("✅ Success!")
    print(f"   URL: {result.url}")
    print(f"   Title: {result.title}")
    print(f"   Status Code: {result.status_code}")
    print(f"   Content length: {len(result.content)} chars")
    print(f"   Fetch duration: {result.fetch_duration:.2f}s")

    return True


async def test_error_handling():
    """Test error handling with invalid URL"""
    print("\n=== Testing Error Handling ===")

    fetch_dep = FetchDependency(timeout_ms=10000)

    # Test with invalid URL
    result = await fetch_dep.fetch_content(
        "https://httpbin.org/status/404",
        browser_config={"headless": True, "humanize": True},
    )

    # 404 should still fetch but with status code 404
    if result.status_code == 404:
        print(f"✅ Properly handled 404: {result.status_code}")
        return True
    elif result.error:
        print(f"✅ Handled error: {result.error}")
        return True
    else:
        print(f"❌ Expected error but got: {result.status_code}")
        return False


async def main():
    """Run basic fetch tests"""
    print("🧪 Testing Fetch Dependency\n")

    success_count = 0
    total_tests = 2

    if await test_basic_fetch():
        success_count += 1

    if await test_error_handling():
        success_count += 1

    print(f"\n📊 Results: {success_count}/{total_tests} tests passed")

    if success_count == total_tests:
        print("✨ All fetch tests completed successfully!")
        return True
    else:
        print("❌ Some tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
