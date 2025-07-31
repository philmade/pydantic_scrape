"""
Proper Camoufox MCP Server using FastMCP pattern.

Provides comprehensive browser automation tools using Camoufox browser.
"""

import asyncio
import base64
from typing import Any, Dict, List, Optional

from loguru import logger
from mcp.server.fastmcp import FastMCP

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    AsyncCamoufox = None


class CamoufoxBrowserManager:
    """Manages Camoufox browser instance and pages"""

    def __init__(self, headless: bool = False):
        self._camoufox_instance: Optional[AsyncCamoufox] = None
        self._browser: Optional[Any] = None
        self._pages: Dict[str, Any] = {}
        self._current_page_id: Optional[str] = None
        self._initialized = False
        self._headless = headless

    async def _ensure_browser(self):
        """Ensure browser is initialized"""
        if not self._initialized or not self._browser:
            try:
                # Clean up any existing instance first
                if self._camoufox_instance:
                    try:
                        await self._camoufox_instance.__aexit__(None, None, None)
                    except:
                        pass

                self._camoufox_instance = AsyncCamoufox(
                    humanize=True,  # Natural cursor movement
                    headless=self._headless,  # Controlled by parameter
                )
                # Use the context manager to get the actual browser
                self._browser = await self._camoufox_instance.__aenter__()

                # Create initial page
                page = await self._browser.new_page()
                page_id = "page_1"
                self._pages = {page_id: page}  # Reset pages dict
                self._current_page_id = page_id

                self._initialized = True
                logger.info("Camoufox browser initialized")
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                self._initialized = False
                raise

    async def _get_current_page(self):
        """Get the current active page"""
        await self._ensure_browser()
        if not self._current_page_id or self._current_page_id not in self._pages:
            # Try to recover by creating a new page
            try:
                page = await self._browser.new_page()
                page_id = "page_1"
                self._pages = {page_id: page}
                self._current_page_id = page_id
                logger.info("Created new page after page loss")
                return page
            except Exception as e:
                logger.error(f"Failed to create new page: {e}")
                raise ValueError("No active page and failed to create new one.")
        
        # Check if the page is still valid
        try:
            page = self._pages[self._current_page_id]
            # Test if page is still responsive
            await page.evaluate("document.readyState")
            return page
        except Exception as e:
            logger.warning(f"Current page became invalid: {e}")
            # Create a new page
            try:
                page = await self._browser.new_page()
                page_id = f"page_{len(self._pages) + 1}"
                self._pages[page_id] = page
                self._current_page_id = page_id
                logger.info("Created new page after page invalidation")
                return page
            except Exception as e:
                logger.error(f"Failed to create replacement page: {e}")
                # Reset browser state
                self._initialized = False
                self._browser = None
                raise ValueError("Page became invalid and failed to create replacement.")

    def _get_page_id(self, page) -> Optional[str]:
        """Get page ID from page object"""
        for page_id, p in self._pages.items():
            if p == page:
                return page_id
        return None

    async def close(self):
        """Cleanup browser resources"""
        if self._camoufox_instance and self._initialized:
            try:
                # Close all pages
                for page in self._pages.values():
                    await page.close()

                await self._camoufox_instance.__aexit__(None, None, None)
                self._initialized = False
                self._pages.clear()
                self._current_page_id = None
                self._browser = None
                self._camoufox_instance = None
                logger.info("Camoufox browser closed successfully")
            except Exception as e:
                logger.error(f"Failed to close browser: {e}")


# Create global browser manager
browser_manager = CamoufoxBrowserManager(headless=False)

# Create the FastMCP server
server = FastMCP("Camoufox Browser Automation Server")


@server.tool()
async def browser_navigate(url: str) -> str:
    """Navigate to a URL"""
    try:
        page = await browser_manager._get_current_page()
        await page.goto(url)
        logger.info(f"Navigated to: {url}")
        return f"Successfully navigated to {url}"
    except Exception as e:
        error_msg = f"Failed to navigate to {url}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_navigate_back() -> str:
    """Navigate back in browser history"""
    try:
        page = await browser_manager._get_current_page()
        await page.go_back()
        return "Successfully navigated back"
    except Exception as e:
        error_msg = f"Failed to navigate back: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_navigate_forward() -> str:
    """Navigate forward in browser history"""
    try:
        page = await browser_manager._get_current_page()
        await page.go_forward()
        return "Successfully navigated forward"
    except Exception as e:
        error_msg = f"Failed to navigate forward: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_click(selector: str) -> str:
    """Click an element by CSS selector"""
    try:
        page = await browser_manager._get_current_page()
        
        # Wait for element to be available and clickable
        try:
            await page.wait_for_selector(selector, timeout=10000)
        except Exception:
            return f"Element {selector} not found within 10 seconds"
        
        await page.click(selector)
        logger.info(f"Clicked element: {selector}")
        return f"Successfully clicked {selector}"
    except Exception as e:
        error_msg = f"Failed to click {selector}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_type(selector: str, text: str) -> str:
    """Type text into an input field"""
    try:
        page = await browser_manager._get_current_page()
        
        # Wait for element to be available first
        try:
            await page.wait_for_selector(selector, timeout=10000)
        except Exception:
            return f"Element {selector} not found within 10 seconds"
        
        # Clear existing text and type new text
        await page.fill(selector, text)
        logger.info(f"Typed text into {selector}")
        return f"Successfully typed '{text}' into {selector}"
    except Exception as e:
        error_msg = f"Failed to type into {selector}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_press_key(key: str) -> str:
    """Press a keyboard key"""
    try:
        page = await browser_manager._get_current_page()
        await page.keyboard.press(key)
        return f"Successfully pressed key: {key}"
    except Exception as e:
        error_msg = f"Failed to press key {key}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_hover(selector: str) -> str:
    """Hover over an element"""
    try:
        page = await browser_manager._get_current_page()
        await page.hover(selector)
        return f"Successfully hovered over {selector}"
    except Exception as e:
        error_msg = f"Failed to hover over {selector}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_take_screenshot(full_page: bool = False, path: str = "/tmp/camoufox_screenshot.png") -> str:
    """Take a screenshot of the current page"""
    try:
        page = await browser_manager._get_current_page()
        await page.screenshot(path=path, full_page=full_page)
        logger.info(f"Screenshot saved to: {path}")
        return f"Screenshot saved to: {path}"
    except Exception as e:
        error_msg = f"Failed to take screenshot: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_get_content() -> str:
    """Get the current page's text content"""
    try:
        page = await browser_manager._get_current_page()
        # Get visible text content
        text_content = await page.inner_text('body')
        
        # Limit content length for processing
        if len(text_content) > 5000:
            text_content = text_content[:5000] + "... [content truncated]"
        
        return text_content
    except Exception as e:
        error_msg = f"Failed to get page content: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_evaluate(script: str) -> str:
    """Execute JavaScript on the current page"""
    try:
        page = await browser_manager._get_current_page()
        result = await page.evaluate(script)
        return f"Script result: {result}"
    except Exception as e:
        error_msg = f"Failed to execute script: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_wait_for_selector(selector: str, timeout: int = 30000) -> str:
    """Wait for an element to appear"""
    try:
        page = await browser_manager._get_current_page()
        await page.wait_for_selector(selector, timeout=timeout)
        return f"Element {selector} appeared"
    except Exception as e:
        error_msg = f"Failed to wait for {selector}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_scroll(direction: str = "down", amount: int = 500) -> str:
    """Scroll the page"""
    try:
        page = await browser_manager._get_current_page()
        if direction.lower() == "down":
            await page.keyboard.press("PageDown")
        elif direction.lower() == "up":
            await page.keyboard.press("PageUp")
        else:
            # Custom scroll using JavaScript
            script = f"window.scrollBy(0, {amount if direction == 'down' else -amount})"
            await page.evaluate(script)
        
        return f"Successfully scrolled {direction}"
    except Exception as e:
        error_msg = f"Failed to scroll: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_get_title() -> str:
    """Get the current page title"""
    try:
        page = await browser_manager._get_current_page()
        title = await page.title()
        return title
    except Exception as e:
        error_msg = f"Failed to get title: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_get_url() -> str:
    """Get the current page URL"""
    try:
        page = await browser_manager._get_current_page()
        url = page.url
        return url
    except Exception as e:
        error_msg = f"Failed to get URL: {str(e)}"
        logger.error(error_msg)
        return error_msg


@server.tool()
async def browser_search_google(query: str) -> str:
    """Navigate to Google and perform a search"""
    try:
        page = await browser_manager._get_current_page()
        
        # Navigate to Google
        await page.goto("https://www.google.com")
        logger.info("Navigated to Google")
        
        # Wait for search box and type query
        search_selector = "textarea[name='q'], input[name='q']"
        try:
            await page.wait_for_selector(search_selector, timeout=10000)
            await page.fill(search_selector, query)
            logger.info(f"Typed search query: {query}")
            
            # Press Enter to search
            await page.keyboard.press("Enter")
            
            # Wait for results to load
            await page.wait_for_selector("#search", timeout=10000)
            logger.info("Search results loaded")
            
            return f"Successfully searched Google for '{query}'"
        except Exception as e:
            return f"Failed to perform search: {str(e)}"
            
    except Exception as e:
        error_msg = f"Failed to search Google: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def cleanup():
    """Cleanup function to close browser"""
    await browser_manager.close()


if __name__ == "__main__":
    try:
        server.run()
    finally:
        asyncio.run(cleanup())