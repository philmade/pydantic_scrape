"""
Scalable Tab-as-Session Agent

Handles multiple processes/scripts trying to use Chrome simultaneously:
- Browser discovery across processes
- Safe connection to existing Chrome instances  
- Fallback to new Chrome instances on different ports
- Process-safe coordination
"""

import asyncio
import json
import os
import socket
from pathlib import Path
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
    """Context for tab session"""
    browser: object = None
    tab: object = None
    tab_id: str = ""


class ScalableChromeManager:
    """Manages Chrome instances across multiple processes safely"""
    
    _browser_instance: Optional[object] = None
    _lock = asyncio.Lock()
    _base_port = 9222
    _max_ports = 10  # Try ports 9222-9231
    _browser_registry_file = Path.home() / ".pydantic_scrape_browsers.json"
    
    @classmethod
    def _get_available_port(cls, start_port: int = None) -> int:
        """Find an available port for Chrome debugging"""
        if start_port is None:
            start_port = cls._base_port
            
        for port in range(start_port, start_port + cls._max_ports):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex(('localhost', port)) != 0:
                    return port
        
        raise RuntimeError(f"No available ports in range {start_port}-{start_port + cls._max_ports}")
    
    @classmethod
    def _get_used_ports(cls) -> List[int]:
        """Get list of ports currently used by Chrome instances"""
        used_ports = []
        for port in range(cls._base_port, cls._base_port + cls._max_ports):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex(('localhost', port)) == 0:
                    used_ports.append(port)
        return used_ports
    
    @classmethod
    def _register_browser(cls, port: int, pid: int):
        """Register a browser instance in the process registry"""
        try:
            registry = {}
            if cls._browser_registry_file.exists():
                with open(cls._browser_registry_file, 'r') as f:
                    registry = json.load(f)
            
            registry[str(port)] = {
                "pid": pid,
                "started_at": asyncio.get_event_loop().time()
            }
            
            with open(cls._browser_registry_file, 'w') as f:
                json.dump(registry, f)
                
            logger.info(f"📝 Registered browser on port {port}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to register browser: {e}")
    
    @classmethod
    def _cleanup_registry(cls):
        """Clean up dead browser entries from registry"""
        try:
            if not cls._browser_registry_file.exists():
                return
                
            with open(cls._browser_registry_file, 'r') as f:
                registry = json.load(f)
            
            # Check which ports are actually in use
            active_ports = cls._get_used_ports()
            
            # Remove entries for ports that are no longer active
            cleaned = {port: info for port, info in registry.items() 
                      if int(port) in active_ports}
            
            with open(cls._browser_registry_file, 'w') as f:
                json.dump(cleaned, f)
                
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup registry: {e}")
    
    @classmethod
    async def _try_connect_to_port(cls, port: int) -> Optional[object]:
        """Try to connect to an existing Chrome instance on a specific port"""
        try:
            import zendriver as zd
            
            logger.info(f"🔍 Trying to connect to Chrome on port {port}")
            
            # Try to connect to existing browser
            browser = await zd.start(port=port)
            
            # Simple test without creating tabs to avoid concurrency issues
            logger.info(f"✅ Connected to existing Chrome on port {port}")
            return browser
            
        except Exception as e:
            logger.debug(f"🔍 Port {port} not available: {str(e)}")
            return None
    
    @classmethod
    async def _start_new_browser(cls, headless: bool = False) -> tuple[object, int]:
        """Start a new Chrome instance on an available port"""
        try:
            import zendriver as zd
            
            # Find available port
            port = cls._get_available_port()
            logger.info(f"🚀 Starting new Chrome instance on port {port}")
            
            # Get Chrome config
            chrome_config = get_popup_blocking_chrome_config(headless=headless)
            
            # Add debugging port
            if "browser_args" not in chrome_config:
                chrome_config["browser_args"] = []
            
            chrome_config["browser_args"].extend([
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
            ])
            
            # Start browser
            browser = await zd.start(**chrome_config)
            await asyncio.sleep(2)
            
            # Register this browser
            cls._register_browser(port, os.getpid())
            
            logger.info(f"✅ New Chrome started on port {port}")
            return browser, port
            
        except Exception as e:
            logger.error(f"❌ Failed to start new Chrome: {e}")
            raise
    
    @classmethod
    async def get_browser(cls, headless: bool = False) -> object:
        """Get a Chrome browser - connect to existing or start new"""
        async with cls._lock:
            if cls._browser_instance is not None:
                return cls._browser_instance
            
            # Clean up dead entries first
            cls._cleanup_registry()
            
            # Try to connect to existing browsers
            used_ports = cls._get_used_ports()
            
            for port in used_ports:
                browser = await cls._try_connect_to_port(port)
                if browser is not None:
                    cls._browser_instance = browser
                    return browser
            
            # No existing browser found, start a new one
            browser, port = await cls._start_new_browser(headless=headless)
            cls._browser_instance = browser
            return browser
    
    @classmethod
    async def cleanup(cls):
        """Clean up browser instance"""
        async with cls._lock:
            if cls._browser_instance is not None:
                try:
                    await cls._browser_instance.stop()
                    logger.info("🧹 Browser instance stopped")
                except Exception as e:
                    logger.warning(f"⚠️ Error stopping browser: {e}")
                finally:
                    cls._browser_instance = None


class ScalableTabAgent:
    """Scalable tab-session agent that works across processes"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.md_converter = MarkItDown()
        
        # Create the browse agent
        self.agent = Agent[str, TabContext](
            "openai:gpt-4o",
            deps_type=TabContext,
            system_prompt="""You are a web browsing agent managing your own tab.

Your tools:
- get_content(): Get clean markdown content from your tab
- get_full_content(): Get complete HTML content if needed
- navigate(url): Navigate your tab to a new URL  
- get_title(): Get your tab's title
- click(selector): Click elements in your tab
- type_text(selector, text): Type into fields in your tab

You have your own tab in a shared Chrome browser that may be used by other processes.
The browser automatically blocks popups and ads.
Focus only on your tab - return detailed results.""",
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
            html_content = await ctx.deps.tab.get_content()
            
            # Clean HTML
            soup = BeautifulSoup(html_content, "lxml")
            
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            
            # Remove popup classes
            popup_classes = ["popup", "modal", "overlay", "cookie", "banner", "consent", "gdpr"]
            for element in soup.find_all(
                attrs={"class": lambda x: x and any(cls in str(x).lower() for cls in popup_classes)}
            ):
                element.decompose()
            
            # Convert to markdown
            cleaned_html = str(soup)
            markdown_content = self.md_converter.convert_stream(cleaned_html).text_content
            
            if len(markdown_content) > 4000:
                markdown_content = markdown_content[:4000] + "\n\n... [content truncated]"
            
            return markdown_content
            
        except Exception as e:
            return f"Failed to get content from tab: {str(e)}"

    async def get_full_content(self, ctx: RunContext[TabContext]) -> str:
        """Get complete HTML content from this tab"""
        try:
            html_content = await ctx.deps.tab.get_content()
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
            await asyncio.sleep(2)
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
        """Browse a single site using scalable tab session"""
        tab = None
        try:
            logger.info(f"🌐 Starting scalable tab session: {task.brief} -> {task.url}")

            # Get browser (existing or new)
            browser = await ScalableChromeManager.get_browser(headless=self.headless)
            
            # Add small delay to avoid concurrency conflicts
            await asyncio.sleep(0.5)
            
            # Create new tab
            tab = await browser.get(task.url, new_tab=True)
            tab_id = f"tab_{id(tab)}"
            
            await asyncio.sleep(3)  # Wait for load

            # Create context
            context = TabContext(browser=browser, tab=tab, tab_id=tab_id)

            # Execute task
            instruction = f"You are in your tab at {task.url}. {task.brief}"
            result = await self.agent.run(instruction, deps=context)

            logger.info(f"✅ Completed scalable tab session for {task.url}")
            return str(result.output)

        except Exception as e:
            import traceback
            error_msg = f"Failed scalable tab browsing {task.url}: {str(e)}"
            full_traceback = traceback.format_exc()
            logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")
            return f"{error_msg}\nTraceback: {full_traceback}"

        finally:
            if tab:
                try:
                    await tab.close()
                    logger.info(f"🧹 Closed scalable tab for {task.url}")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing tab: {e}")


# Convenience function for parallel scalable browsing
async def browse_sites_scalable(tasks: List[BrowseTask], headless: bool = False) -> str:
    """
    Browse multiple sites using scalable tab sessions across processes.

    Args:
        tasks: List of BrowseTask objects
        headless: Whether to run browser in headless mode

    Returns:
        Combined results from all browsing sessions
    """
    if not tasks:
        return "No browsing tasks provided"

    logger.info(f"🚀 Starting {len(tasks)} scalable tab sessions")

    async def run_scalable_agent(task: BrowseTask) -> tuple[str, str]:
        """Run a single scalable tab agent"""
        agent = ScalableTabAgent(headless=headless)
        result = await agent.browse_site(task)
        return task.url, result

    try:
        # Execute all agents in parallel
        results = await asyncio.gather(
            *[run_scalable_agent(task) for task in tasks]
        )

        # Combine results
        combined_results = []
        for url, result in results:
            combined_results.append(f"=== {url} ===\n{result}\n")

        final_result = "\n".join(combined_results)
        logger.info(f"✅ Completed {len(tasks)} scalable tab sessions")
        return final_result
        
    except Exception as e:
        logger.error(f"❌ Scalable tab sessions failed: {e}")
        return f"Failed to execute scalable tab sessions: {str(e)}"


# Browser management functions
async def cleanup_scalable_browser():
    """Clean up the scalable browser instance"""
    await ScalableChromeManager.cleanup()


# Export main functions
__all__ = ["browse_sites_scalable", "ScalableTabAgent", "BrowseTask", "cleanup_scalable_browser"]