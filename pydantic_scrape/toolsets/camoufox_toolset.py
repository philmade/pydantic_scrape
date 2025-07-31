"""
Direct Camoufox toolset with proper browser lifecycle management.

Manages browser state within the agent lifecycle rather than through MCP.
"""

from typing import Any, Optional

from loguru import logger

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    AsyncCamoufox = None


class CamoufoxToolset:
    """Direct browser automation toolset with lifecycle management"""

    def __init__(self, headless: bool = False):
        if not CAMOUFOX_AVAILABLE:
            raise ImportError(
                "Camoufox is not available. Install with: pip install pydantic-scrape[camoufox]\n"
                "Note: Camoufox is now legacy - consider using Chawan browser instead."
            )
        self._camoufox_instance: Optional[AsyncCamoufox] = None
        self._browser: Optional[Any] = None
        self._page: Optional[Any] = None
        self._headless = headless
        self._initialized = False

    async def __aenter__(self):
        """Initialize browser when entering context"""
        await self._initialize_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup browser when exiting context"""
        await self._cleanup_browser()

    async def _initialize_browser(self):
        """Initialize the browser instance"""
        if self._initialized:
            return

        try:
            logger.info("Initializing Camoufox browser...")
            self._camoufox_instance = AsyncCamoufox(
                humanize=True,
                headless=self._headless,
            )

            # Enter the context manager
            self._browser = await self._camoufox_instance.__aenter__()

            # Create initial page
            self._page = await self._browser.new_page()

            self._initialized = True
            logger.info("✅ Camoufox browser initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize browser: {e}")
            await self._cleanup_browser()
            raise

    async def _cleanup_browser(self):
        """Cleanup browser resources"""
        if not self._initialized:
            return

        try:
            logger.info("Cleaning up Camoufox browser...")

            if self._page:
                await self._page.close()
                self._page = None

            if self._camoufox_instance:
                await self._camoufox_instance.__aexit__(None, None, None)
                self._camoufox_instance = None
                self._browser = None

            self._initialized = False
            logger.info("✅ Browser cleanup completed")

        except Exception as e:
            logger.error(f"⚠️  Error during browser cleanup: {e}")

    async def _ensure_page(self):
        """Ensure we have a valid page"""
        if not self._initialized or not self._page:
            await self._initialize_browser()

        # Test if page is still valid
        try:
            await self._page.evaluate("document.readyState")
        except Exception:
            # Page became invalid, create a new one
            logger.warning("Page became invalid, creating new page")
            self._page = await self._browser.new_page()

        return self._page

    # Browser navigation tools
    async def navigate(self, url: str) -> str:
        """Navigate to a URL"""
        try:
            page = await self._ensure_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"🌐 Navigated to: {url}")
            return f"Successfully navigated to {url}"
        except Exception as e:
            error_msg = f"Failed to navigate to {url}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def navigate_back(self) -> str:
        """Navigate back in browser history"""
        try:
            page = await self._ensure_page()
            await page.go_back()
            return "Successfully navigated back"
        except Exception as e:
            error_msg = f"Failed to navigate back: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def navigate_forward(self) -> str:
        """Navigate forward in browser history"""
        try:
            page = await self._ensure_page()
            await page.go_forward()
            return "Successfully navigated forward"
        except Exception as e:
            error_msg = f"Failed to navigate forward: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    # Page interaction tools
    async def click(self, selector: str) -> str:
        """Click an element by CSS selector"""
        try:
            page = await self._ensure_page()

            # Wait for element to be available
            await page.wait_for_selector(selector, timeout=10000)
            await page.click(selector)

            logger.info(f"👆 Clicked element: {selector}")
            return f"Successfully clicked {selector}"
        except Exception as e:
            error_msg = f"Failed to click {selector}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def type_text(self, selector: str, text: str) -> str:
        """Type text into an input field"""
        try:
            page = await self._ensure_page()

            # Wait for element to be available
            await page.wait_for_selector(selector, timeout=10000)
            await page.fill(selector, text)

            logger.info(f"⌨️  Typed text into {selector}")
            return f"Successfully typed '{text}' into {selector}"
        except Exception as e:
            error_msg = f"Failed to type into {selector}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def press_key(self, key: str) -> str:
        """Press a keyboard key"""
        try:
            page = await self._ensure_page()
            await page.keyboard.press(key)
            return f"Successfully pressed key: {key}"
        except Exception as e:
            error_msg = f"Failed to press key {key}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def hover(self, selector: str) -> str:
        """Hover over an element"""
        try:
            page = await self._ensure_page()
            await page.wait_for_selector(selector, timeout=10000)
            await page.hover(selector)
            return f"Successfully hovered over {selector}"
        except Exception as e:
            error_msg = f"Failed to hover over {selector}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    # Information gathering tools
    async def get_content(self) -> str:
        """Get the current page's text content"""
        try:
            page = await self._ensure_page()
            text_content = await page.inner_text("body")

            # Limit content length
            if len(text_content) > 5000:
                text_content = text_content[:5000] + "... [content truncated]"

            return text_content
        except Exception as e:
            error_msg = f"Failed to get page content: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def get_title(self) -> str:
        """Get the current page title"""
        try:
            page = await self._ensure_page()
            title = await page.title()
            return title
        except Exception as e:
            error_msg = f"Failed to get title: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def get_url(self) -> str:
        """Get the current page URL"""
        try:
            page = await self._ensure_page()
            return page.url
        except Exception as e:
            error_msg = f"Failed to get URL: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def take_screenshot(self, path: str = "/tmp/camoufox_screenshot.png") -> str:
        """Take a screenshot of the current page"""
        try:
            page = await self._ensure_page()
            await page.screenshot(path=path, full_page=False)
            logger.info(f"📸 Screenshot saved to: {path}")
            return f"Screenshot saved to: {path}"
        except Exception as e:
            error_msg = f"Failed to take screenshot: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> str:
        """Wait for an element to appear"""
        try:
            page = await self._ensure_page()
            await page.wait_for_selector(selector, timeout=timeout)
            return f"Element {selector} appeared"
        except Exception as e:
            error_msg = f"Failed to wait for {selector}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def scroll(self, direction: str = "down") -> str:
        """Scroll the page"""
        try:
            page = await self._ensure_page()

            if direction.lower() == "down":
                await page.keyboard.press("PageDown")
            elif direction.lower() == "up":
                await page.keyboard.press("PageUp")
            else:
                await page.keyboard.press("PageDown")  # Default to down

            return f"Successfully scrolled {direction}"
        except Exception as e:
            error_msg = f"Failed to scroll: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def evaluate_javascript(self, script: str) -> str:
        """Execute JavaScript on the current page"""
        try:
            page = await self._ensure_page()
            result = await page.evaluate(script)
            return f"Script result: {result}"
        except Exception as e:
            error_msg = f"Failed to execute script: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def search_google(self, query: str) -> str:
        """Navigate to Google and perform a search"""
        try:
            page = await self._ensure_page()

            # Navigate to Google
            await page.goto("https://www.google.com", wait_until="domcontentloaded")
            logger.info("🔍 Navigated to Google")

            # Wait for and fill search box
            search_selector = "textarea[name='q'], input[name='q']"
            await page.wait_for_selector(search_selector, timeout=10000)
            await page.fill(search_selector, query)
            logger.info(f"🔍 Typed search query: {query}")

            # Press Enter to search
            await page.keyboard.press("Enter")

            # Wait for results
            await page.wait_for_selector("#search", timeout=15000)
            logger.info("📄 Search results loaded")

            return f"Successfully searched Google for '{query}'"

        except Exception as e:
            error_msg = f"Failed to search Google: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg
