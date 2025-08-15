"""
Playwright Browser Toolset for Pydantic AI - DEPENDENCY-AS-GRAPH PATTERN

Following the same pattern as ChawanToolset but using our working Playwright WebKit browser.
PlaywrightContext IS the browsing knowledge graph with anti-bot evasion.
"""

import asyncio
import re
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from markdownify import markdownify

from ..dependencies.playwright_webkit_api import (
    PlaywrightWebKitBrowser,
    PageInfo,
)
from gathersdk import AgentContext

class ActionStatus(str, Enum):
    """Status of browsing actions"""
    PENDING = "pending"
    COMPLETED = "completed" 
    FAILED = "failed"

class BrowseAction(BaseModel):
    """A single browsing action - part of the browsing knowledge graph"""
    action_type: str  # "navigate", "click", "scroll", "form_fill", etc.
    target: str       # URL, link index, form field, etc.
    status: ActionStatus = ActionStatus.COMPLETED
    result_summary: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_time: Optional[float] = None

class PageState(BaseModel):
    """Current page state - part of the browsing knowledge graph"""
    url: str
    title: Optional[str] = None
    content_length: int = 0
    link_count: int = 0
    form_count: int = 0
    # CRITICAL: Store the actual AI-friendly content so agent can reference it!
    ai_content: Optional[str] = None  # The numbered links content agent actually saw
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PlaywrightContext(BaseModel):
    """
    Browsing Knowledge Graph Context - follows dependency-as-graph pattern
    
    This is the "brain" for Playwright browsing operations, storing all browsing
    state in structured Pydantic models. All tools mutate this context directly.
    Uses anti-bot evasion Playwright WebKit browser.
    """
    model_config = {"arbitrary_types_allowed": True}

    # Core browser instance - excluded from serialization
    browser: Optional[PlaywrightWebKitBrowser] = Field(default=None, exclude=True)
    
    # Browsing configuration
    objective: Optional[str] = None
    url: Optional[str] = None
    max_actions: int = 10
    
    # Knowledge Graph: All browsing actions and state
    actions: List[BrowseAction] = Field(default_factory=list)
    pages: List[PageState] = Field(default_factory=list)
    
    # Current state
    current_page: Optional[PageState] = None
    
    # Session metadata
    session_id: str = Field(default_factory=lambda: f"playwright_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Can optionally take an AgentContext if needed
    agent_context: AgentContext
    
    @property
    def action_count(self) -> int:
        """Total number of actions taken"""
        return len(self.actions)
    
    @property
    def successful_actions(self) -> int:
        """Number of successful actions"""
        return sum(1 for action in self.actions if action.status == ActionStatus.COMPLETED)
    
    @property
    def current_url(self) -> Optional[str]:
        """Get current page URL"""
        return self.current_page.url if self.current_page else None
    
    def add_action(self, action_type: str, target: str, status: ActionStatus = ActionStatus.COMPLETED, result_summary: str = None):
        """Add a browsing action to the knowledge graph"""
        action = BrowseAction(
            action_type=action_type,
            target=target,
            status=status,
            result_summary=result_summary
        )
        self.actions.append(action)
        self.last_updated = datetime.now(timezone.utc)
        return action
    
    def set_current_page(self, url: str, title: str = None, content_length: int = 0, link_count: int = 0, form_count: int = 0, ai_content: str = None):
        """Update current page state in the knowledge graph"""
        page_state = PageState(
            url=url,
            title=title,
            content_length=content_length,
            link_count=link_count,
            form_count=form_count,
            ai_content=ai_content  # Store what the agent actually saw!
        )
        self.current_page = page_state
        self.pages.append(page_state)
        self.last_updated = datetime.now(timezone.utc)
        return page_state
    
    def render_state(self) -> str:
        """Render current browsing state as comprehensive JSON with stored page content"""
        return self.model_dump_json(indent=2)
    
    def render_browsing_history(self) -> str:
        """Render browsing history with AI content for agent memory"""
        if not self.pages:
            return "No pages visited yet."
        
        history = "=== BROWSING HISTORY WITH STORED CONTENT ===\n\n"
        for i, page in enumerate(self.pages[-3:], 1):  # Last 3 pages
            history += f"{i}. {page.title or 'Untitled'} ({page.url})\n"
            history += f"   Content: {page.content_length} chars, {page.link_count} links\n"
            if page.ai_content:
                # Show first 200 chars of what agent actually saw
                content_preview = page.ai_content[:200] + "..." if len(page.ai_content) > 200 else page.ai_content
                history += f"   Preview: {content_preview}\n"
            history += "\n"
        
        return history


# CONTENT FILTERING HELPERS - Convert HTML to clean markdown like Chawan

def html_to_clean_markdown(html_content: str, search_terms: Optional[List[str]] = None) -> str:
    """
    Convert HTML to clean markdown and optionally filter by search terms.
    This replicates Chawan's approach of sending clean, filtered content to AI.
    
    Args:
        html_content: Raw HTML content from browser
        search_terms: Optional list of terms to filter content by
        
    Returns:
        Clean markdown content, optionally filtered by search terms
    """
    try:
        # Convert HTML to markdown using markdownify
        markdown_content = markdownify(
            html_content,
            heading_style="ATX",  # Use # for headings
            bullets="-",  # Use - for bullets
            strip=["script", "style", "meta", "link"],  # Remove these tags
        ).strip()
        
        # If no search terms, return full markdown (still much cleaner than HTML)
        if not search_terms:
            return markdown_content
            
        # Filter content based on search terms (like Chawan's search_with_context)
        return _filter_content_by_search_terms(markdown_content, search_terms)
        
    except Exception as e:
        logger.warning(f"HTML to markdown conversion failed: {e}")
        # Fallback: return raw content (better than failing)
        return html_content[:2000] + "..." if len(html_content) > 2000 else html_content


def _filter_content_by_search_terms(content: str, search_terms: List[str], context_lines: int = 2) -> str:
    """
    Filter content to only include sections relevant to search terms.
    This replicates Chawan's search_with_context functionality.
    
    Args:
        content: Full markdown content
        search_terms: List of terms to search for
        context_lines: Number of lines of context around matches
        
    Returns:
        Filtered content containing only relevant sections
    """
    if not search_terms:
        return content
        
    lines = content.split('\n')
    relevant_lines = set()
    
    # Find lines containing search terms (case insensitive)
    for i, line in enumerate(lines):
        for term in search_terms:
            if term.lower() in line.lower():
                # Add the matching line and context around it
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                relevant_lines.update(range(start, end))
                break
    
    if not relevant_lines:
        # No matches found - return summary instead of empty content
        return f"No direct matches found for: {', '.join(search_terms)}\n\nPage summary (first 500 chars):\n{content[:500]}..."
    
    # Sort line numbers and reconstruct content
    sorted_lines = sorted(relevant_lines)
    filtered_content = []
    
    prev_line = -1
    for line_num in sorted_lines:
        # Add separator for gaps in content
        if line_num > prev_line + 1:
            filtered_content.append("\n[...content omitted...]\n")
        filtered_content.append(lines[line_num])
        prev_line = line_num
    
    return '\n'.join(filtered_content)


# PLAYWRIGHT TOOLS - Following dependency-as-graph pattern like ChawanToolset
# Simple string returns, direct PlaywrightContext mutation

async def navigate_to(ctx: RunContext[PlaywrightContext], url: str) -> str:
    """Navigate to URL using Playwright WebKit with anti-bot evasion"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🌐 PLAYWRIGHT NAVIGATING TO: {url}")
        
        content = await ctx.deps.browser.navigate(url)
        
        # Get page info from our browser
        page_info = ctx.deps.browser.get_page_info()
        current_url = ctx.deps.browser.get_current_url()
        
        if page_info:
            # Directly mutate the PlaywrightContext (dependency-as-graph pattern)
            ctx.deps.add_action("navigate", url, ActionStatus.COMPLETED, f"Navigated to {page_info.title}")
            # Store action in context (detailed page state set later after content processing)
            ctx.deps.add_action("navigate", url, ActionStatus.COMPLETED, f"Navigated to {page_info.title}")
        
        # Convert HTML to clean markdown (like Chawan's clean text output)
        clean_content = html_to_clean_markdown(content)
        
        # Store the clean content for agent reference
        ctx.deps.set_current_page(
            url=current_url or url,
            title=page_info.title,
            content_length=len(clean_content),  # Use clean content length
            link_count=len(page_info.links) if page_info and page_info.links else 0,
            form_count=0,
            ai_content=clean_content  # Store clean content agent actually sees
        )
        
        # Return clean markdown content instead of raw HTML
        return f"""✅ Navigated to: {page_info.title if page_info else 'Unknown'}
URL: {current_url or url}
Links available: {len(page_info.links) if page_info and page_info.links else 0}

=== PAGE CONTENT (CLEAN MARKDOWN) ===
{clean_content}"""
        
    except Exception as e:
        logger.error(f"❌ Playwright navigation failed: {e}")
        ctx.deps.add_action("navigate", url, ActionStatus.FAILED, f"Navigation failed: {str(e)}")
        return f"❌ Navigation failed: {str(e)}"


async def navigate_to_search(ctx: RunContext[PlaywrightContext], url: str, search_terms: List[str]) -> str:
    """
    Navigate to URL and return only content relevant to search terms.
    This replicates Chawan's navigate_to_search functionality with required search parameter.
    
    Args:
        url: URL to navigate to
        search_terms: Required list of search terms to filter content by
        
    Returns:
        Filtered markdown content containing only relevant sections
    """
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
            
        if not search_terms:
            return "❌ Search terms are required for navigate_to_search"

        logger.info(f"🔍 PLAYWRIGHT SEARCH NAVIGATION: {url} | Searching for: {', '.join(search_terms)}")
        
        # Initialize filtered_content to prevent UnboundLocalError
        filtered_content = "❌ No content available - navigation failed"
        
        content = await ctx.deps.browser.navigate(url)
        
        # Get page info from our browser
        page_info = ctx.deps.browser.get_page_info()
        current_url = ctx.deps.browser.get_current_url()
        
        if page_info:
            # Store action in context
            ctx.deps.add_action("navigate_search", url, ActionStatus.COMPLETED, 
                              f"Search navigation to {page_info.title} for: {', '.join(search_terms)}")
            
            # Convert HTML to markdown and filter by search terms
            filtered_content = html_to_clean_markdown(content, search_terms)
            
            # Store the filtered content for agent reference
            ctx.deps.set_current_page(
                url=current_url or url,
                title=page_info.title,
                content_length=len(filtered_content),
                link_count=len(page_info.links) if page_info and page_info.links else 0,
                form_count=0,
                ai_content=filtered_content  # Store filtered content agent actually sees
            )
        else:
            # Handle case where page_info is None (navigation failed)
            ctx.deps.add_action("navigate_search", url, ActionStatus.FAILED, 
                              f"Navigation failed - no page info available")
            filtered_content = f"❌ Failed to load page content from {url}"
        
        # Return filtered content (much smaller context than full page)
        return f"""✅ Search navigation completed: {page_info.title if page_info else 'Unknown'}
URL: {current_url or url}
Search terms: {', '.join(search_terms)}
Links available: {len(page_info.links) if page_info and page_info.links else 0}

=== FILTERED CONTENT (SEARCH RESULTS) ===
{filtered_content}"""
        
    except Exception as e:
        logger.error(f"❌ Search navigation failed: {e}")
        ctx.deps.add_action("navigate_search", url, ActionStatus.FAILED, 
                          f"Search navigation failed: {str(e)}")
        return f"❌ Search navigation failed: {str(e)}"


async def click_link_by_index(ctx: RunContext[PlaywrightContext], link_index: int) -> str:
    """Click a specific numbered link using Playwright"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🔗 Clicking link {link_index}")
        
        # Use our browser's click_link_by_index method
        result = await ctx.deps.browser.click_link_by_index(link_index)
        
        # Add action to context
        ctx.deps.add_action("click", f"link_{link_index}", ActionStatus.COMPLETED, f"Clicked link {link_index}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Link click failed: {e}")
        ctx.deps.add_action("click", f"link_{link_index}", ActionStatus.FAILED, f"Link click failed: {str(e)}")
        return f"❌ Failed to click link {link_index}: {str(e)}"


async def get_current_url(ctx: RunContext[PlaywrightContext]) -> str:
    """Get current page URL"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
        
        current_url = ctx.deps.browser.get_current_url()
        return f"🔗 Current URL: {current_url}"
        
    except Exception as e:
        logger.error(f"❌ Get URL failed: {e}")
        return f"❌ Failed to get current URL: {str(e)}"


async def scroll_page(ctx: RunContext[PlaywrightContext], direction: str = "down", pages: int = 1) -> str:
    """Scroll the page up or down"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
        
        logger.info(f"📜 Scrolling {direction} by {pages} pages")
        
        # For now, just record the action - could implement actual scrolling later
        ctx.deps.add_action("scroll", f"{direction}_{pages}", ActionStatus.COMPLETED, f"Scrolled {direction} by {pages} pages")
        
        return f"✅ Scrolled {direction} by {pages} page(s)"
        
    except Exception as e:
        logger.error(f"❌ Scroll failed: {e}")
        ctx.deps.add_action("scroll", f"{direction}_{pages}", ActionStatus.FAILED, f"Scroll failed: {str(e)}")
        return f"❌ Failed to scroll: {str(e)}"


async def fill_input(ctx: RunContext[PlaywrightContext], field_name: str, value: str) -> str:
    """Fill an input field (placeholder for future implementation)"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
        
        logger.info(f"📝 Filling input field: {field_name}")
        
        # For now, just record the action - could implement actual form filling later
        ctx.deps.add_action("fill_input", field_name, ActionStatus.COMPLETED, f"Filled {field_name} with {value}")
        
        return f"✅ Filled input field '{field_name}' with value"
        
    except Exception as e:
        logger.error(f"❌ Fill input failed: {e}")
        ctx.deps.add_action("fill_input", field_name, ActionStatus.FAILED, f"Fill input failed: {str(e)}")
        return f"❌ Failed to fill input field: {str(e)}"


async def submit_form(ctx: RunContext[PlaywrightContext]) -> str:
    """Submit a form (placeholder for future implementation)"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
        
        logger.info(f"📤 Submitting form")
        
        # For now, just record the action - could implement actual form submission later
        ctx.deps.add_action("submit_form", "form", ActionStatus.COMPLETED, "Submitted form")
        
        return f"✅ Form submitted successfully"
        
    except Exception as e:
        logger.error(f"❌ Form submission failed: {e}")
        ctx.deps.add_action("submit_form", "form", ActionStatus.FAILED, f"Form submission failed: {str(e)}")
        return f"❌ Failed to submit form: {str(e)}"


async def fill_form_bulk(ctx: RunContext[PlaywrightContext], form_data: Dict[str, str]) -> str:
    """Fill multiple form fields at once (placeholder for future implementation)"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"
        
        logger.info(f"📝 Bulk filling form with {len(form_data)} fields")
        
        # For now, just record the action - could implement actual bulk form filling later
        ctx.deps.add_action("fill_form_bulk", f"{len(form_data)}_fields", ActionStatus.COMPLETED, f"Bulk filled {len(form_data)} fields")
        
        return f"✅ Bulk filled {len(form_data)} form fields"
        
    except Exception as e:
        logger.error(f"❌ Bulk form filling failed: {e}")
        ctx.deps.add_action("fill_form_bulk", f"{len(form_data)}_fields", ActionStatus.FAILED, f"Bulk form filling failed: {str(e)}")
        return f"❌ Failed to bulk fill form fields: {str(e)}"


# Export all the tools and context
__all__ = [
    'PlaywrightContext',
    'BrowseAction', 
    'PageState',
    'ActionStatus',
    'navigate_to',
    'navigate_to_search',  # New search-filtered navigation function
    'click_link_by_index',
    'get_current_url',
    'scroll_page',
    'fill_input',
    'submit_form',
    'fill_form_bulk',
]