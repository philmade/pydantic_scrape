"""
Playwright WebKit Browser API - Anti-Bot Detection Evasion

A fast, stealth browser implementation using Playwright WebKit with:
- Anti-bot detection evasion (navigator.webdriver = false)
- Realistic fingerprinting and user agents
- No CSS/images loading for speed
- HTML to numbered links processing (like CHAWAN)
- playwright-extra stealth plugins
"""

import asyncio
import re
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from playwright_stealth import Stealth

@dataclass
class PageInfo:
    """Information about a browsed page"""
    url: str
    title: Optional[str] = None
    content_length: int = 0
    links: List[Dict[str, str]] = None
    load_time: float = 0.0
    
    def __post_init__(self):
        if self.links is None:
            self.links = []

class PlaywrightWebKitBrowser:
    """
    Fast, stealth WebKit browser with anti-bot evasion.
    
    Features:
    - WebKit engine (faster than Chromium for simple browsing)
    - Anti-bot detection evasion
    - Realistic user agents and fingerprinting
    - No CSS/images for speed
    - HTML to numbered links conversion
    """
    
    def __init__(self, debug: bool = False, timeout: int = 30, enable_images: bool = False):
        self.debug = debug
        self.timeout = timeout
        self.enable_images = enable_images
        
        # Browser instances
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Current page state
        self.current_url: Optional[str] = None
        self.page_content: Optional[str] = None
        self.page_info: Optional[PageInfo] = None
        
        # Realistic user agents (updated 2024)
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
    
    async def start(self):
        """Start the browser with anti-bot evasion"""
        try:
            if self.debug:
                logger.info("🚀 Starting Playwright WebKit browser with stealth mode")
            
            self.playwright = await async_playwright().start()
            
            # Use WebKit for speed (lighter than Chromium)
            # WebKit doesn't support Chromium-specific args, so use minimal args
            self.browser = await self.playwright.webkit.launch(
                headless=True,  # Always headless for server use
            )
            
            # Create context with realistic fingerprinting
            import random
            user_agent = random.choice(self.user_agents)
            
            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1366, "height": 768},  # Common resolution
                locale="en-US",
                timezone_id="America/New_York",
                # Block resources for speed
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }
            )
            
            # Block unnecessary resources for speed
            await self.context.route("**/*", self._handle_route)
            
            # Create page
            self.page = await self.context.new_page()
            
            # Apply stealth techniques
            stealth = Stealth()
            await stealth.apply_stealth_async(self.page)
            
            # Additional anti-detection measures
            await self.page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                
                // Mock chrome property
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                };
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5].map((x) => ({ length: x })),
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                // Mock permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
            """)
            
            if self.debug:
                logger.info(f"✅ Browser started with user agent: {user_agent[:50]}...")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start browser: {e}")
            await self.close()
            return False
    
    async def _handle_route(self, route):
        """Handle resource routing for speed optimization"""
        resource_type = route.request.resource_type
        
        # Block images and stylesheets by default for speed
        if resource_type in ['image', 'stylesheet', 'font'] and not self.enable_images:
            await route.abort()
        # Block ads and tracking
        elif any(domain in route.request.url for domain in [
            'googletagmanager.com', 'google-analytics.com', 'facebook.com/tr',
            'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
            'outbrain.com', 'taboola.com', 'adsystem.com'
        ]):
            await route.abort()
        else:
            await route.continue_()
    
    async def navigate(self, url: str) -> str:
        """Navigate to URL and return processed content with numbered links"""
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")
        
        start_time = datetime.now()
        
        try:
            if self.debug:
                logger.info(f"🌐 Navigating to: {url}")
            
            # Navigate with timeout
            response = await self.page.goto(
                url, 
                wait_until="domcontentloaded",  # Don't wait for all resources
                timeout=self.timeout * 1000
            )
            
            if not response or response.status >= 400:
                error_msg = f"Failed to load page (status: {response.status if response else 'unknown'})"
                logger.error(error_msg)
                return error_msg
            
            # Wait briefly for dynamic content
            await asyncio.sleep(0.5)
            
            # Get page info
            title = await self.page.title()
            self.current_url = self.page.url
            
            # Get HTML content
            html_content = await self.page.content()
            
            # Process HTML to numbered links format (like CHAWAN)
            processed_content = self._process_html_to_numbered_links(html_content, url)
            
            # Calculate load time
            load_time = (datetime.now() - start_time).total_seconds()
            
            # Store page info
            self.page_info = PageInfo(
                url=self.current_url,
                title=title,
                content_length=len(processed_content),
                load_time=load_time
            )
            
            self.page_content = processed_content
            
            if self.debug:
                logger.info(f"✅ Navigation complete: {title} ({len(processed_content)} chars, {load_time:.2f}s)")
            
            return processed_content
            
        except Exception as e:
            error_msg = f"Navigation failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _process_html_to_numbered_links(self, html: str, base_url: str) -> str:
        """Process HTML to numbered links format similar to CHAWAN"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Extract text content
            text_content = soup.get_text()
            
            # Clean up whitespace
            lines = [line.strip() for line in text_content.splitlines()]
            text_content = '\n'.join(line for line in lines if line)
            
            # Find all links
            links = []
            for i, link in enumerate(soup.find_all('a', href=True), 1):
                href = link.get('href')
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith('/'):
                        from urllib.parse import urljoin
                        href = urljoin(base_url, href)
                    elif not href.startswith('http'):
                        continue
                    
                    link_text = link.get_text().strip()
                    if link_text and len(link_text) > 2:  # Only meaningful links
                        links.append({
                            'index': i,
                            'url': href,
                            'text': link_text[:100]  # Truncate long link text
                        })
            
            # Format like CHAWAN: text content with numbered links at the end
            if links:
                numbered_links = "\n\nNUMBERED LINKS:\n"
                for link in links[:50]:  # Limit to 50 links for readability
                    numbered_links += f"[{link['index']}] {link['text']} → {link['url']}\n"
                
                # Store links in page info
                if self.page_info:
                    self.page_info.links = links
                
                return f"{text_content}\n{numbered_links}"
            else:
                return text_content
                
        except Exception as e:
            logger.warning(f"⚠️ HTML processing error: {e}")
            # Return raw HTML if processing fails
            return html
    
    def get_current_url(self) -> Optional[str]:
        """Get current page URL"""
        return self.current_url
    
    def get_page_info(self) -> Optional[PageInfo]:
        """Get current page information"""
        return self.page_info
    
    async def get_content_with_numbered_links(self) -> Optional[str]:
        """Get current page content with numbered links"""
        return self.page_content
    
    async def click_link_by_index(self, link_index: int) -> str:
        """Click a numbered link (if we stored them)"""
        if not self.page_info or not self.page_info.links:
            return "❌ No links available to click"
        
        # Find link by index
        target_link = None
        for link in self.page_info.links:
            if link['index'] == link_index:
                target_link = link
                break
        
        if not target_link:
            return f"❌ Link {link_index} not found"
        
        try:
            # Navigate to the link URL
            result = await self.navigate(target_link['url'])
            return f"✅ Clicked link {link_index}: {target_link['text']}\n\n{result}"
        except Exception as e:
            return f"❌ Failed to click link {link_index}: {str(e)}"
    
    async def close(self):
        """Clean up browser resources"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            if self.debug:
                logger.info("🛑 Browser closed successfully")
                
        except Exception as e:
            logger.warning(f"⚠️ Error closing browser: {e}")

# Convenience function for quick testing
async def quick_browse(url: str, debug: bool = True, timeout: int = 30) -> str:
    """Quick browse function for testing"""
    browser = PlaywrightWebKitBrowser(debug=debug, timeout=timeout)
    
    try:
        await browser.start()
        result = await browser.navigate(url)
        return result
    finally:
        await browser.close()

# Export main classes
__all__ = ['PlaywrightWebKitBrowser', 'PageInfo', 'quick_browse']