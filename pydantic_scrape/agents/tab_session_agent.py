"""
Tab-as-Session Browse Agent

Revolutionary approach:
- One persistent Chrome instance with popup blocking
- Each agent connects to the same browser
- Each agent manages only their own tab
- Perfect for parallel browsing without profile conflicts
- Chrome stays open, agents come and go
"""

import asyncio
from typing import List, Optional

from bs4 import BeautifulSoup
from loguru import logger
from markitdown import MarkItDown
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from pydantic_scrape.utils.chrome_extensions import get_popup_blocking_chrome_config


class BrowseTask(BaseModel):
    """Single browse task specification"""
    url: str
    brief: str


class TabContext(BaseModel):
    """Context for tab session - holds browser and tab reference"""
    browser: object = None
    tab: object = None
    tab_id: str = ""


class TabSessionManager:
    """Manages tab sessions within a single browser instance"""
    
    _browser_instance: Optional[object] = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_browser(cls, headless: bool = False) -> object:
        """Get or create the browser instance for this script run"""
        async with cls._lock:
            if cls._browser_instance is None:
                logger.info("🚀 Starting browser for tab sessions")
                
                import zendriver as zd
                chrome_config = get_popup_blocking_chrome_config(headless=headless)
                cls._browser_instance = await zd.start(**chrome_config)
                
                # Wait for browser to be ready
                await asyncio.sleep(2)
                logger.info("✅ Browser ready for tab sessions")
            
            return cls._browser_instance
    
    @classmethod
    async def cleanup(cls):
        """Clean up the browser instance"""
        async with cls._lock:
            if cls._browser_instance is not None:
                try:
                    await cls._browser_instance.stop()
                    logger.info("🧹 Browser instance stopped")
                except Exception as e:
                    logger.warning(f"⚠️ Error stopping browser: {e}")
                finally:
                    cls._browser_instance = None


class TabSessionAgent:
    """Browse agent that uses tab-as-session architecture"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.md_converter = MarkItDown()
        
        # Create the browse agent for tab sessions
        self.agent = Agent[str, TabContext](
            "openai:gpt-4o",
            deps_type=TabContext,
            system_prompt="""You are a web browsing agent managing your own tab session.

Your tools:
- get_content(): Get clean markdown content from your tab
- get_full_content(): Get complete HTML content if needed
- navigate(url): Navigate your tab to a new URL  
- get_title(): Get your tab's title
- click(selector): Click elements in your tab
- type_text(selector, text): Type into fields in your tab

You have your own dedicated tab in a shared Chrome browser.
The browser automatically blocks popups and ads.
Focus only on your tab - other agents have their own tabs.
Return detailed results of your actions.""",
        )
        
        # Add tools
        self.agent.tool(self.get_content)
        self.agent.tool(self.get_full_content)
        self.agent.tool(self.navigate)
        self.agent.tool(self.get_title)
        self.agent.tool(self.click)
        self.agent.tool(self.type_text)

    async def get_content(self, ctx: RunContext[TabContext]) -> str:
        """Get clean markdown content from this tab"""
        try:
            # Get HTML content from our tab
            html_content = await ctx.deps.tab.get_content()
            
            # Clean HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, "lxml")
            
            # Remove noise elements
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            
            # Remove popup classes (backup cleanup)
            popup_classes = ["popup", "modal", "overlay", "cookie", "banner", "consent", "gdpr"]
            for element in soup.find_all(
                attrs={"class": lambda x: x and any(cls in str(x).lower() for cls in popup_classes)}
            ):
                element.decompose()
            
            # Convert to markdown
            cleaned_html = str(soup)
            markdown_content = self.md_converter.convert_stream(cleaned_html).text_content
            
            # Limit size
            if len(markdown_content) > 4000:
                markdown_content = markdown_content[:4000] + "\n\n... [content truncated]"
            
            return markdown_content
            
        except Exception as e:
            return f"Failed to get content from tab: {str(e)}"

    async def get_full_content(self, ctx: RunContext[TabContext]) -> str:
        """Get complete HTML content from this tab"""
        try:
            html_content = await ctx.deps.tab.get_content()
            
            # Basic cleanup
            soup = BeautifulSoup(html_content, "lxml")
            for element in soup(["script", "style"]):
                element.decompose()
            
            text_content = soup.get_text(separator=" ", strip=True)
            
            if len(text_content) > 6000:
                text_content = text_content[:6000] + "\n\n... [content truncated]"
            
            return text_content
            
        except Exception as e:
            return f"Failed to get full content from tab: {str(e)}"

    async def navigate(self, ctx: RunContext[TabContext], url: str) -> str:
        """Navigate this tab to a new URL"""
        try:
            await ctx.deps.tab.get(url)
            await asyncio.sleep(2)  # Wait for load
            return f"Successfully navigated tab to {url}"
        except Exception as e:
            return f"Failed to navigate tab: {str(e)}"

    async def get_title(self, ctx: RunContext[TabContext]) -> str:
        """Get this tab's title"""
        try:
            title = await ctx.deps.tab.evaluate("document.title")
            return str(title)
        except Exception as e:
            return f"Failed to get tab title: {str(e)}"

    async def click(self, ctx: RunContext[TabContext], selector: str) -> str:
        """Click elements in this tab"""
        try:
            element = await ctx.deps.tab.select(selector)
            if element:
                await element.click()
                await asyncio.sleep(1)
                return f"Successfully clicked {selector} in tab"
            else:
                return f"Element not found in tab: {selector}"
        except Exception as e:
            return f"Failed to click in tab: {str(e)}"

    async def type_text(self, ctx: RunContext[TabContext], selector: str, text: str) -> str:
        """Type into fields in this tab"""
        try:
            element = await ctx.deps.tab.select(selector)
            if element:
                await element.clear_input()
                await element.send_keys(text)
                return f"Successfully typed '{text}' into {selector} in tab"
            else:
                return f"Element not found in tab: {selector}"
        except Exception as e:
            return f"Failed to type in tab: {str(e)}"

    async def browse_site(self, task: BrowseTask) -> str:
        """
        Browse a single site using tab-as-session architecture.

        Args:
            task: Single BrowseTask object with url and brief

        Returns:
            String with result from browsing session
        """
        tab = None
        try:
            logger.info(f"🌐 Starting tab session for: {task.brief} -> {task.url}")

            # Get the browser for this script run
            browser = await TabSessionManager.get_browser(headless=self.headless)
            
            # Create a new tab for this session
            tab = await browser.get(task.url, new_tab=True)
            tab_id = f"tab_{id(tab)}"
            
            # Wait for tab to load and extensions to process
            await asyncio.sleep(3)

            # Create tab context
            context = TabContext(browser=browser, tab=tab, tab_id=tab_id)

            # Execute browsing task in our dedicated tab
            instruction = f"You are in your own tab at {task.url}. {task.brief}"
            result = await self.agent.run(instruction, deps=context)

            logger.info(f"✅ Completed tab session for {task.url}")
            return str(result.output)

        except Exception as e:
            import traceback
            error_msg = f"Failed to browse {task.url} in tab session: {str(e)}"
            full_traceback = traceback.format_exc()
            logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")
            return f"{error_msg}\nTraceback: {full_traceback}"

        finally:
            # Close only our tab, not the browser
            if tab:
                try:
                    await tab.close()
                    logger.info(f"🧹 Closed tab session for {task.url}")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing tab: {e}")


# Convenience function for parallel tab sessions
async def browse_sites_parallel_tabs(tasks: List[BrowseTask], headless: bool = False) -> str:
    """
    Browse multiple sites using parallel tab sessions in one Chrome browser.

    Args:
        tasks: List of BrowseTask objects with url and brief
        headless: Whether to run browser in headless mode

    Returns:
        String with combined results from all tab sessions
    """
    if not tasks:
        return "No browsing tasks provided"

    logger.info(f"🚀 Starting {len(tasks)} parallel tab sessions")

    async def run_tab_session(task: BrowseTask) -> tuple[str, str]:
        """Run a single tab session for one task"""
        agent = TabSessionAgent(headless=headless)
        result = await agent.browse_site(task)
        return task.url, result

    try:
        # Execute all tab sessions in parallel
        results = await asyncio.gather(
            *[run_tab_session(task) for task in tasks]
        )

        # Combine results
        combined_results = []
        for url, result in results:
            combined_results.append(f"=== {url} ===\n{result}\n")

        final_result = "\n".join(combined_results)
        logger.info(f"✅ Completed {len(tasks)} parallel tab sessions")
        return final_result
        
    except Exception as e:
        logger.error(f"❌ Parallel tab sessions failed: {e}")
        return f"Failed to execute parallel tab sessions: {str(e)}"


# Functions for browser management
async def cleanup_browser():
    """Clean up the browser instance when done with script"""
    await TabSessionManager.cleanup()


# Export the main functions and classes
__all__ = ["browse_sites_parallel_tabs", "TabSessionAgent", "BrowseTask", "cleanup_browser"]