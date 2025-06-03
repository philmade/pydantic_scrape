"""
Batch Scraping Dependency - Concurrent execution of full scrape graphs

Universal dependency for running multiple scrape operations concurrently
while managing resources and providing detailed progress tracking.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


@dataclass
class BatchScrapeResult:
    """Result from batch scraping operations"""

    results: List[Any]  # List of FinalScrapeResult or similar
    total_processed: int
    successful_scrapes: int
    failed_scrapes: int
    total_time_seconds: float
    average_time_per_url: float
    processing_errors: List[str]
    url_timing: Dict[str, float]  # URL -> time taken


class BatchScrapingDependency:
    """
    Universal dependency for concurrent scraping operations.

    Can execute any scraping function (like execute_full_scrape_graph)
    concurrently across multiple URLs with resource management.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout_per_url: float = 60.0,
        retry_failed: bool = True,
        max_retries: int = 1,
    ):
        """
        Initialize batch scraping dependency.

        Args:
            max_concurrent: Maximum concurrent scraping operations
            timeout_per_url: Timeout per individual scrape operation (seconds)
            retry_failed: Whether to retry failed operations
            max_retries: Maximum number of retries per URL
        """
        self.max_concurrent = max_concurrent
        self.timeout_per_url = timeout_per_url
        self.retry_failed = retry_failed
        self.max_retries = max_retries

        logger.info(
            f"BatchScraping: Initialized with {max_concurrent} concurrent tasks, {timeout_per_url}s timeout"
        )

    async def scrape_urls_concurrent(
        self,
        urls: List[str],
        scrape_function: Callable,
        scrape_kwargs: Optional[Dict] = None,
    ) -> BatchScrapeResult:
        """
        Scrape multiple URLs concurrently using the provided scrape function.

        Args:
            urls: List of URLs to scrape
            scrape_function: Async function to call for each URL (e.g., execute_full_scrape_graph)
            scrape_kwargs: Additional kwargs to pass to scrape_function

        Returns:
            BatchScrapeResult with all scraping results and performance metrics
        """
        start_time = time.time()
        scrape_kwargs = scrape_kwargs or {}

        logger.info(f"BatchScraping: Starting concurrent scraping of {len(urls)} URLs")

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)
        url_timing = {}

        async def scrape_single_url(url: str, attempt: int = 1):
            """Scrape a single URL with timeout and retry logic"""
            async with semaphore:
                url_start = time.time()
                try:
                    logger.info(f"BatchScraping: Processing {url} (attempt {attempt})")

                    # Execute the scrape function with timeout
                    result = await asyncio.wait_for(
                        scrape_function(url, **scrape_kwargs),
                        timeout=self.timeout_per_url,
                    )

                    url_time = time.time() - url_start
                    url_timing[url] = url_time

                    logger.info(f"BatchScraping: ✅ Completed {url} in {url_time:.2f}s")
                    return result

                except asyncio.TimeoutError:
                    url_time = time.time() - url_start
                    url_timing[url] = url_time

                    error_msg = f"Timeout after {self.timeout_per_url}s"
                    logger.error(f"BatchScraping: ⏰ {url} - {error_msg}")

                    # Retry if enabled and attempts remaining
                    if self.retry_failed and attempt <= self.max_retries:
                        logger.info(
                            f"BatchScraping: 🔄 Retrying {url} (attempt {attempt + 1})"
                        )
                        return await scrape_single_url(url, attempt + 1)

                    return self._create_error_result(url, error_msg)

                except Exception as e:
                    url_time = time.time() - url_start
                    url_timing[url] = url_time

                    error_msg = str(e)
                    logger.error(f"BatchScraping: ❌ {url} - {error_msg}")

                    # Retry if enabled and attempts remaining
                    if self.retry_failed and attempt <= self.max_retries:
                        logger.info(
                            f"BatchScraping: 🔄 Retrying {url} (attempt {attempt + 1})"
                        )
                        return await scrape_single_url(url, attempt + 1)

                    return self._create_error_result(url, error_msg)

        # Execute all scraping tasks concurrently
        logger.info(
            f"BatchScraping: Launching {len(urls)} concurrent tasks (max {self.max_concurrent})"
        )

        scrape_tasks = [scrape_single_url(url) for url in urls]
        results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        # Analyze results
        successful_results = []
        failed_results = []
        processing_errors = []

        for i, result in enumerate(results):
            url = urls[i]

            if isinstance(result, Exception):
                error_msg = f"{url}: {str(result)}"
                processing_errors.append(error_msg)
                failed_results.append(self._create_error_result(url, str(result)))
            else:
                # Check if the result indicates success
                if hasattr(result, "success") and result.success:
                    successful_results.append(result)
                elif hasattr(result, "error"):
                    # This is an error result we created
                    processing_errors.append(f"{url}: {result.error}")
                    failed_results.append(result)
                else:
                    # Assume success if no clear error indicator
                    successful_results.append(result)

        total_time = time.time() - start_time
        avg_time = total_time / len(urls) if urls else 0

        logger.info(
            f"BatchScraping: 🏁 Completed in {total_time:.2f}s - {len(successful_results)} success, {len(failed_results)} failed"
        )
        logger.info(f"BatchScraping: 📈 Average time per URL: {avg_time:.2f}s")

        # Log timing breakdown
        if url_timing:
            fastest = min(url_timing.values())
            slowest = max(url_timing.values())
            logger.info(
                f"BatchScraping: ⚡ Fastest: {fastest:.2f}s, Slowest: {slowest:.2f}s"
            )

        return BatchScrapeResult(
            results=successful_results + failed_results,  # Include all results
            total_processed=len(urls),
            successful_scrapes=len(successful_results),
            failed_scrapes=len(failed_results),
            total_time_seconds=total_time,
            average_time_per_url=avg_time,
            processing_errors=processing_errors,
            url_timing=url_timing,
        )

    def _create_error_result(self, url: str, error_message: str):
        """Create a standardized error result object"""
        # Try to create a FinalScrapeResult-like object for consistency
        try:
            from ..graphs.full_scrape_graph import FinalScrapeResult

            return FinalScrapeResult(
                url=url,
                success=False,
                content_type="error",
                confidence=0.0,
                fetch_attempts=0,
                metadata_complete=False,
                full_text_extracted=False,
                pdf_links_found=0,
                processing_errors=[error_message],
            )
        except ImportError:
            # Fallback to a simple dict if FinalScrapeResult not available
            return {
                "url": url,
                "success": False,
                "error": error_message,
                "content_type": "error",
            }

    async def scrape_with_progress(
        self,
        urls: List[str],
        scrape_function: Callable,
        progress_callback: Optional[Callable] = None,
        scrape_kwargs: Optional[Dict] = None,
    ) -> BatchScrapeResult:
        """
        Scrape URLs with real-time progress reporting.

        Args:
            urls: List of URLs to scrape
            scrape_function: Async scraping function
            progress_callback: Optional callback function called with (completed, total, current_url)
            scrape_kwargs: Additional kwargs for scrape_function

        Returns:
            BatchScrapeResult with detailed metrics
        """
        if not progress_callback:
            # Default progress callback that just logs
            def default_progress(completed, total, current_url):
                logger.info(
                    f"BatchScraping: Progress {completed}/{total} - Current: {current_url}"
                )

            progress_callback = default_progress

        # We'll modify the scrape function to include progress reporting
        completed_count = 0

        async def scrape_with_progress_tracking(url):
            nonlocal completed_count

            # Call original scrape function
            result = await scrape_function(url, **(scrape_kwargs or {}))

            # Update progress
            completed_count += 1
            progress_callback(completed_count, len(urls), url)

            return result

        # Use the regular concurrent scraping with progress tracking
        return await self.scrape_urls_concurrent(
            urls,
            scrape_with_progress_tracking,
            scrape_kwargs={},  # Already included in wrapper
        )


# Convenience function for notebook testing
async def test_batch_scraping(urls: List[str], max_concurrent: int = 3):
    """Test function for notebook use - now uses browser-optimized batch scraping"""

    from ..graphs.full_scrape_graph import execute_batch_scrape_graph

    print(
        f"🚀 Testing browser-optimized batch scraping with {len(urls)} URLs, max {max_concurrent} concurrent..."
    )

    # Use the new browser-optimized batch scraping for better performance
    result = await execute_batch_scrape_graph(
        urls=urls,
        max_concurrent=max_concurrent,
        timeout_per_url=60.0
    )

    print("\n✅ Browser-optimized batch scraping completed!")
    print(f"⏱️  Total time: {result.total_time_seconds:.2f}s")
    print(f"🔧 Browser setup: {result.browser_setup_time:.2f}s")
    print(f"⚡ Actual scraping: {result.actual_scraping_time:.2f}s")
    print(f"📈 Average per URL: {result.average_time_per_url:.2f}s")
    print(f"✅ Successful: {result.successful_scrapes}/{result.total_processed}")
    print(f"❌ Failed: {result.failed_scrapes}")

    if result.processing_errors:
        print("\n❌ Errors:")
        for error in result.processing_errors:
            print(f"   {error}")

    print("\n⚡ Per-URL timing:")
    for url, timing in result.url_timing.items():
        status = "🚀" if timing < 5 else "✅" if timing < 10 else "⚠️"
        print(f"   {status} {timing:.2f}s - {url}")

    return result
