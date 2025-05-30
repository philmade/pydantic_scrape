"""
Basic fetch dependency example - using the FetchDependency directly
"""

import asyncio

from pydantic_scrape.dependencies import FetchDependency


async def basic_fetch():
    """Simple fetch example with Camoufox"""
    print("=== Basic Fetch Example ===")

    fetch_dep = FetchDependency(timeout_ms=30000)

    # Fetch with Camoufox browser automation
    result = await fetch_dep.fetch_content(
        "https://example.com", browser_config={"headless": True, "humanize": True}
    )

    if result.error:
        print(f"Error: {result.error}")
        return

    print(f"URL: {result.url}")
    print(f"Title: {result.title}")
    print(f"Status Code: {result.status_code}")
    print(f"Content length: {len(result.content)} chars")
    print(f"Fetch duration: {result.fetch_duration:.2f}s")

    # Show first 200 characters of content
    if result.content:
        print("\nFirst 200 characters:")
        print(
            result.content[:200] + "..."
            if len(result.content) > 200
            else result.content
        )


async def fetch_with_custom_config():
    """Fetch with custom browser configuration"""
    print("\n=== Custom Browser Config Example ===")

    fetch_dep = FetchDependency(timeout_ms=15000)

    # Custom configuration
    browser_config = {
        "headless": False,  # Show browser window
        "humanize": False,  # Disable human-like behavior for speed
        "addons": [],  # No additional addons
    }

    result = await fetch_dep.fetch_content(
        "https://httpbin.org/html", browser_config=browser_config
    )

    if result.error:
        print(f"Error: {result.error}")
        return

    print(f"Fetched: {result.url}")
    print(f"Title: {result.title}")
    print(f"Duration: {result.fetch_duration:.2f}s")
    print(f"Content type detected: {len(result.content)} chars")


async def fetch_multiple():
    """Fetch multiple URLs to demonstrate reusability"""
    print("\n=== Multiple URLs Example ===")

    fetch_dep = FetchDependency(timeout_ms=20000)

    urls = [
        "https://httpbin.org/html",
        "https://example.com",
        "https://httpbin.org/json",
    ]

    for i, url in enumerate(urls, 1):
        print(f"\nFetching {i}/{len(urls)}: {url}")

        result = await fetch_dep.fetch_content(
            url, browser_config={"headless": True, "humanize": True}
        )

        if result.error:
            print(f"❌ Error: {result.error}")
        else:
            print(f"✅ Success: {result.title} ({len(result.content)} chars)")


async def main():
    """Run all fetch examples"""
    print("🌐 Pydantic Scrape: Fetch Dependency Examples\n")

    await basic_fetch()
    await fetch_with_custom_config()
    await fetch_multiple()

    print("\n✨ All fetch examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
