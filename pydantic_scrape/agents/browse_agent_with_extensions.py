"""
Enhanced Browse Agent with Chrome Extensions for Popup Blocking

This agent uses Chrome extensions instead of JavaScript for popup dismissal:
- uBlock Origin for ad/popup blocking
- Chrome flags for notification/geolocation blocking  
- Custom Chrome profile with privacy settings
- Much more reliable than JavaScript-based popup dismissal
"""

import asyncio
from typing import List

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


class BrowseContext(BaseModel):
    """Context for browse agent - holds browser instance and current page"""
    browser: object = None
    page: object = None
    headless: bool = False


class ExtensionBrowseAgent:
    """Browse agent with Chrome extensions for automatic popup blocking"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.md_converter = MarkItDown()
        
        # Create the browse agent with clean tools
        self.agent = Agent[str, BrowseContext](
            "openai:gpt-4o",
            deps_type=BrowseContext,
            system_prompt="""You are a web browsing agent with automatic popup blocking. Your tools:

- get_content(): Get clean markdown content from the current page  
- get_full_content(): Get complete HTML content if markdown isn't sufficient
- navigate(url): Navigate to a new URL
- get_title(): Get page title
- click(selector): Click elements by CSS selector
- type_text(selector, text): Type into input fields

Chrome extensions automatically handle popups, cookies, and ads.
You start on the target page with clean, popup-free content.
Use get_content() for readable markdown, get_full_content() for detailed HTML.
Return detailed results of your actions.""",
        )
        
        # Add tools to the agent
        self.agent.tool(self.get_content)
        self.agent.tool(self.get_full_content)
        self.agent.tool(self.navigate)
        self.agent.tool(self.get_title)
        self.agent.tool(self.click)
        self.agent.tool(self.type_text)

    async def get_content(self, ctx: RunContext[BrowseContext]) -> str:
        """Get clean markdown content from the current page"""
        try:
            # Get HTML content
            html_content = await ctx.deps.page.get_content()
            
            # Clean HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, "lxml")
            
            # Remove script, style, nav, header, footer elements
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            
            # Remove common popup/banner classes (backup cleanup)
            popup_classes = [
                "popup", "modal", "overlay", "cookie", "banner", "consent", "gdpr"
            ]
            for element in soup.find_all(
                attrs={
                    "class": lambda x: x
                    and any(cls in str(x).lower() for cls in popup_classes)
                }
            ):
                element.decompose()
            
            # Convert cleaned HTML to markdown
            cleaned_html = str(soup)
            markdown_content = self.md_converter.convert_stream(
                cleaned_html
            ).text_content
            
            # Limit content size
            if len(markdown_content) > 4000:
                markdown_content = (
                    markdown_content[:4000] + "\n\n... [content truncated]"
                )
            
            return markdown_content
            
        except Exception as e:
            return f"Failed to get content: {str(e)}"

    async def get_full_content(self, ctx: RunContext[BrowseContext]) -> str:
        """Get complete HTML content if markdown conversion isn't sufficient"""
        try:
            html_content = await ctx.deps.page.get_content()
            
            # Basic cleanup only
            soup = BeautifulSoup(html_content, "lxml")
            for element in soup(["script", "style"]):
                element.decompose()
            
            text_content = soup.get_text(separator=" ", strip=True)
            
            if len(text_content) > 6000:
                text_content = text_content[:6000] + "\n\n... [content truncated]"
            
            return text_content
            
        except Exception as e:
            return f"Failed to get full content: {str(e)}"

    async def navigate(self, ctx: RunContext[BrowseContext], url: str) -> str:
        """Navigate to a new URL"""
        try:
            ctx.deps.page = await ctx.deps.browser.get(url, new_tab=True)
            await asyncio.sleep(2)  # Wait for load and extensions to work
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Failed to navigate: {str(e)}"

    async def get_title(self, ctx: RunContext[BrowseContext]) -> str:
        """Get page title"""
        try:
            title = await ctx.deps.page.evaluate("document.title")
            return str(title)
        except Exception as e:
            return f"Failed to get title: {str(e)}"

    async def click(self, ctx: RunContext[BrowseContext], selector: str) -> str:
        """Click elements by CSS selector"""
        try:
            element = await ctx.deps.page.select(selector)
            if element:
                await element.click()
                await asyncio.sleep(1)  # Wait for any response
                return f"Successfully clicked {selector}"
            else:
                return f"Element not found: {selector}"
        except Exception as e:
            return f"Failed to click {selector}: {str(e)}"

    async def type_text(self, ctx: RunContext[BrowseContext], selector: str, text: str) -> str:
        """Type into input fields"""
        try:
            element = await ctx.deps.page.select(selector)
            if element:
                await element.clear_input()
                await element.send_keys(text)
                return f"Successfully typed '{text}' into {selector}"
            else:
                return f"Element not found: {selector}"
        except Exception as e:
            return f"Failed to type into {selector}: {str(e)}"

    async def browse_site(self, task: BrowseTask) -> str:
        """
        Browse a single site with Chrome extensions for popup blocking.

        Args:
            task: Single BrowseTask object with url and brief

        Returns:
            String with result from browsing session
        """
        import zendriver as zd

        browser = None
        try:
            logger.info(f"🌐 Starting Chrome with extensions for: {task.brief} -> {task.url}")

            # Get Chrome configuration with popup blocking
            chrome_config = get_popup_blocking_chrome_config(headless=self.headless)
            
            # Create browser instance with extensions
            browser = await zd.start(**chrome_config)
            await asyncio.sleep(2)  # Wait for browser and extensions to load

            # Navigate to target URL
            page = await browser.get(task.url)
            await asyncio.sleep(4)  # Wait longer for extensions to process page

            # Create context
            context = BrowseContext(browser=browser, page=page, headless=self.headless)

            # Execute browsing task (no manual popup dismissal needed!)
            instruction = f"You are on {task.url}. {task.brief}"
            result = await self.agent.run(instruction, deps=context)

            logger.info(f"✅ Completed extension-powered browsing {task.url}")
            return str(result.output)

        except Exception as e:
            import traceback
            error_msg = f"Failed to browse {task.url}: {str(e)}"
            full_traceback = traceback.format_exc()
            logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")
            return f"{error_msg}\nTraceback: {full_traceback}"

        finally:
            # Clean up browser
            if browser:
                try:
                    await browser.stop()
                    logger.info(f"🧹 Extension-powered browser stopped for {task.url}")
                except Exception as e:
                    logger.error(f"⚠️  Error cleaning up browser: {e}")


# Convenience function for parallel extension-powered browsing
async def browse_sites_with_extensions(tasks: List[BrowseTask], headless: bool = False) -> str:
    """
    Browse multiple sites with Chrome extensions for popup blocking.

    Args:
        tasks: List of BrowseTask objects with url and brief
        headless: Whether to run browser in headless mode

    Returns:
        String with combined results from all browsing sessions
    """
    if not tasks:
        return "No browsing tasks provided"

    logger.info(f"🚀 Parallelizing {len(tasks)} extension-powered BrowseAgent instances")

    async def run_extension_agent(task: BrowseTask) -> tuple[str, str]:
        """Run a single extension-powered BrowseAgent for one task"""
        agent = ExtensionBrowseAgent(headless=headless)
        result = await agent.browse_site(task)
        return task.url, result

    # Execute all agents in parallel
    results = await asyncio.gather(
        *[run_extension_agent(task) for task in tasks]
    )

    # Combine results
    combined_results = []
    for url, result in results:
        combined_results.append(f"=== {url} ===\n{result}\n")

    final_result = "\n".join(combined_results)
    logger.info(f"✅ Completed extension-powered parallel browsing with {len(tasks)} agents")
    return final_result


# Export the main functions and classes
__all__ = ["browse_sites_with_extensions", "ExtensionBrowseAgent", "BrowseTask"]