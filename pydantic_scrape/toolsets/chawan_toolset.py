"""
Chawan Browser Toolset for Pydantic AI - REFACTORED FOR DEPENDENCY-AS-GRAPH PATTERN

Following the same pattern as DeepAgent - simple string returns, direct context mutation.
ChawanContext IS the browsing knowledge graph.
"""

import asyncio
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from pydantic_scrape.dependencies.chawan_browser_api import (
    ChawanBrowser,
    Direction,
    PageInfo,
)

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

class ChawanContext(BaseModel):
    """
    Browsing Knowledge Graph Context - follows dependency-as-graph pattern
    
    This is the "brain" for chawan browsing operations, storing all browsing
    state in structured Pydantic models. All tools mutate this context directly.
    """
    model_config = {"arbitrary_types_allowed": True}

    # Core browser instance - excluded from serialization
    browser: Optional[ChawanBrowser] = Field(default=None, exclude=True)
    
    # Browsing configuration
    objective: Optional[str] = None
    max_actions: int = 10
    
    # Knowledge Graph: All browsing actions and state
    actions: List[BrowseAction] = Field(default_factory=list)
    pages: List[PageState] = Field(default_factory=list)
    
    # Current state
    current_page: Optional[PageState] = None
    
    # Session metadata
    session_id: str = Field(default_factory=lambda: f"browse_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
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
        for i, page in enumerate(self.pages[-3:], 1):  # Show last 3 pages
            history += f"[{i}] {page.title} ({page.url})\n"
            if page.ai_content:
                # Show first 500 chars of AI content so agent remembers what was there
                content_preview = page.ai_content[:500] + "..." if len(page.ai_content) > 500 else page.ai_content
                history += f"Content preview:\n{content_preview}\n"
            history += "-" * 60 + "\n\n"
        
        return history


# REFACTORED TOOLS - Following dependency-as-graph pattern like DeepAgent
# Simple string returns, direct ChawanContext mutation

async def navigate_to(ctx: RunContext[ChawanContext], url: str) -> str:
    """Navigate to URL and return page content with numbered links - agent needs to SEE the page!"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🌐 NAVIGATING TO: {url}")
        
        content = await ctx.deps.browser.navigate(url)
        
        # Get AI-friendly content with numbered links - CRITICAL FOR AGENT TO SEE!
        ai_content = await ctx.deps.browser.get_content_with_numbered_links()
        page_info = await ctx.deps.browser.get_page_info()
        
        # Directly mutate the ChawanContext (dependency-as-graph pattern)
        ctx.deps.add_action("navigate", url, ActionStatus.COMPLETED, f"Navigated to {page_info.title}")
        ctx.deps.set_current_page(
            url=url,
            title=page_info.title,
            content_length=page_info.content_length,
            link_count=len(page_info.links),
            form_count=0,  # PageInfo doesn't have form_count, using default
            ai_content=ai_content  # CRITICAL: Store what agent actually saw!
        )
        
        # Return the actual page content so agent can see what's there!
        return f"""✅ Navigated to: {page_info.title}
URL: {ctx.deps.browser.get_current_url()}
Links available: {len(page_info.links)}

=== PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}"""
        
    except Exception as e:
        logger.error(f"❌ Navigation failed: {e}")
        ctx.deps.add_action("navigate", url, ActionStatus.FAILED, f"Navigation failed: {str(e)}")
        return f"❌ Navigation failed: {str(e)}"


async def click_link_by_index(ctx: RunContext[ChawanContext], link_index: int) -> str:
    """Click a specific numbered link and return new page content - agent needs to SEE the result!"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🔗 Clicking link {link_index}")
        
        old_url = ctx.deps.browser.get_current_url()
        content = await ctx.deps.browser.click_link_by_index(link_index)
        new_url = ctx.deps.browser.get_current_url()
        
        # Get AI-friendly content with numbered links - CRITICAL FOR AGENT TO SEE!
        ai_content = await ctx.deps.browser.get_content_with_numbered_links()
        page_info = await ctx.deps.browser.get_page_info()
        
        # Directly mutate the ChawanContext (dependency-as-graph pattern)
        ctx.deps.add_action("click_link", f"link[{link_index}]", ActionStatus.COMPLETED, f"Clicked link {link_index} → {page_info.title}")
        
        if old_url != new_url:
            ctx.deps.set_current_page(
                url=new_url,
                title=page_info.title,
                content_length=page_info.content_length,
                link_count=len(page_info.links),
                form_count=0,  # PageInfo doesn't have form_count, using default
                ai_content=ai_content  # CRITICAL: Store what agent saw after clicking!
            )
        
        # Return the actual page content so agent can see what's there after clicking!
        navigation_info = ""
        if old_url != new_url:
            navigation_info = f"🔄 Navigated from {old_url} to {new_url}\n\n"
        
        return f"""✅ Clicked link {link_index} successfully!
{navigation_info}New Page: {page_info.title}
URL: {new_url}
Links available: {len(page_info.links)}

=== NEW PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}"""
        
    except Exception as e:
        logger.error(f"❌ Link {link_index} click failed: {e}")
        ctx.deps.add_action("click_link", f"link[{link_index}]", ActionStatus.FAILED, f"Link click failed: {str(e)}")
        return f"❌ Link {link_index} click failed: {str(e)}"


async def scroll_page(ctx: RunContext[ChawanContext], direction: str, n: int = 1) -> str:
    """Scroll page in specified direction and return updated content - agent needs to see what's revealed!"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"📜 Scrolling {direction} by {n} pages")
        
        direction_enum = Direction(direction.lower())
        success = await ctx.deps.browser.scroll_page(direction_enum, n)
        
        if success:
            # Get updated content after scroll - CRITICAL FOR AGENT TO SEE!
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
            page_info = await ctx.deps.browser.get_page_info()
            
            # Directly mutate the ChawanContext (dependency-as-graph pattern)
            ctx.deps.add_action("scroll", f"{direction}:{n}", ActionStatus.COMPLETED, f"Scrolled {direction} by {n} pages")
            
            # Update current page state with new content info
            if ctx.deps.current_page:
                ctx.deps.current_page.content_length = page_info.content_length
                ctx.deps.current_page.link_count = len(page_info.links)
                ctx.deps.last_updated = datetime.now(timezone.utc)
            
            # Return the updated page content so agent can see new content revealed by scroll!
            return f"""✅ Scrolled {direction} by {n} pages
Current Page: {page_info.title}
Links visible: {len(page_info.links)}

=== UPDATED PAGE CONTENT AFTER SCROLL ===
{ai_content}"""
        else:
            ctx.deps.add_action("scroll", f"{direction}:{n}", ActionStatus.FAILED, "Scroll failed")
            return f"❌ Failed to scroll {direction}"
        
    except Exception as e:
        logger.error(f"❌ Scroll failed: {e}")
        ctx.deps.add_action("scroll", f"{direction}:{n}", ActionStatus.FAILED, f"Scroll error: {str(e)}")
        return f"❌ Scroll failed: {str(e)}"


async def fill_input(ctx: RunContext[ChawanContext], text: str) -> str:
    """Fill current input field - simple string return, mutates ChawanContext directly"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"📝 Filling input: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        success = await ctx.deps.browser.fill_input(text)
        
        if success:
            # Directly mutate the ChawanContext (dependency-as-graph pattern)
            ctx.deps.add_action("fill_input", text[:50], ActionStatus.COMPLETED, f"Filled input with '{text[:30]}...'")
            return f"✅ Input filled: '{text[:50]}{'...' if len(text) > 50 else ''}'"
        else:
            ctx.deps.add_action("fill_input", text[:50], ActionStatus.FAILED, "Input fill failed")
            return "❌ Failed to fill input field"
        
    except Exception as e:
        logger.error(f"❌ Input filling failed: {e}")
        ctx.deps.add_action("fill_input", text[:50], ActionStatus.FAILED, f"Input error: {str(e)}")
        return f"❌ Input filling failed: {str(e)}"


async def submit_form(ctx: RunContext[ChawanContext]) -> str:
    """Submit current form - simple string return, mutates ChawanContext directly"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        old_url = ctx.deps.browser.get_current_url()
        logger.info(f"📤 Submitting form on: {old_url}")
        
        content = await ctx.deps.browser.submit_form()
        new_url = ctx.deps.browser.get_current_url()
        page_info = await ctx.deps.browser.get_page_info()
        
        # Directly mutate the ChawanContext (dependency-as-graph pattern)
        ctx.deps.add_action("submit_form", old_url, ActionStatus.COMPLETED, f"Form submitted → {page_info.title}")
        
        if old_url != new_url:
            # Get AI content for the new page after form submission
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
            ctx.deps.set_current_page(
                url=new_url,
                title=page_info.title,
                content_length=page_info.content_length,
                link_count=len(page_info.links),
                form_count=0,  # PageInfo doesn't have form_count, using default
                ai_content=ai_content  # Store what agent saw after form submission!
            )
        
        return f"✅ Form submitted → {page_info.title}"
        
    except Exception as e:
        logger.error(f"❌ Form submission failed: {e}")
        ctx.deps.add_action("submit_form", ctx.deps.current_url or "unknown", ActionStatus.FAILED, f"Form error: {str(e)}")
        return f"❌ Form submission failed: {str(e)}"


async def get_current_url(ctx: RunContext[ChawanContext]) -> str:
    """Get current page URL - simple string return, reads from ChawanContext"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        url = ctx.deps.browser.get_current_url()
        return f"Current URL: {url}"

    except Exception as e:
        return f"❌ Failed to get current URL: {str(e)}"


# Missing functions added back for API compatibility - refactored for dependency-as-graph pattern

async def navigate_to_with_search(ctx: RunContext[ChawanContext], url: str, search_terms: List[str] = None) -> str:
    """Navigate to URL and optionally search for specific terms - returns page content or focused search results"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🌐 NAVIGATING WITH SEARCH TO: {url}")
        if search_terms:
            logger.info(f"🔍 SEARCH TERMS: {search_terms}")
        
        content = await ctx.deps.browser.navigate(url)
        page_info = await ctx.deps.browser.get_page_info()
        
        # Directly mutate the ChawanContext
        ctx.deps.add_action("navigate_search", url, ActionStatus.COMPLETED, 
                          f"Navigated to {page_info.title} with search terms: {search_terms}")
        
        # Get AI content for storage
        if not search_terms:
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
        else:
            ai_content = None  # Don't store full content for search results
            
        ctx.deps.set_current_page(
            url=url,
            title=page_info.title,
            content_length=page_info.content_length,
            link_count=len(page_info.links),
            form_count=0,  # PageInfo doesn't have form_count, using default
            ai_content=ai_content  # Store what agent saw (if no search)
        )
        
        # If no search terms, return full page content with numbered links
        if not search_terms:
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
            return f"""✅ Navigated to: {page_info.title}
URL: {url}
Links available: {len(page_info.links)}

=== PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}"""
        
        # Search for terms and return focused results
        full_content = await ctx.deps.browser.get_content()
        search_results = []
        content_lines = full_content.split('\n')
        
        for term in search_terms:
            term_matches = []
            for i, line in enumerate(content_lines):
                if term.lower() in line.lower():
                    context_start = max(0, i - 1)
                    context_end = min(len(content_lines), i + 2)
                    context = '\n'.join(content_lines[context_start:context_end])
                    term_matches.append(f"Line {i+1}:\n{context}")
            
            if term_matches:
                search_results.append((term, term_matches[:3]))  # Limit to 3 matches per term
        
        if search_results:
            result = f"""✅ Navigated to {page_info.title} with focused search
URL: {url}

🎯 SEARCH RESULTS:
"""
            for term, matches in search_results:
                result += f"\n📍 Found '{term}':\n"
                for match in matches:
                    result += f"{match}\n---\n"
            
            # Also include available links
            result += f"\n🔗 Available links: {len(page_info.links)}"
            return result
        else:
            # If no search terms found, still return the page content so agent can see it
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
            return f"""✅ Navigated to {page_info.title} - search terms not found
URL: {url}

⚠️ Search terms '{', '.join(search_terms)}' not found. Showing full page:

=== PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}"""
        
    except Exception as e:
        logger.error(f"❌ Navigation with search failed: {e}")
        ctx.deps.add_action("navigate_search", url, ActionStatus.FAILED, f"Navigation failed: {str(e)}")
        return f"❌ Navigation with search failed: {str(e)}"


async def multi_search_page(ctx: RunContext[ChawanContext], search_terms: List[str]) -> str:
    """Search current page for multiple terms - simple string return"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"🔍 MULTI-SEARCH: {len(search_terms)} terms on current page")
        
        content = await ctx.deps.browser.get_content()
        page_info = await ctx.deps.browser.get_page_info()
        
        found_terms = []
        for term in search_terms:
            if term.lower() in content.lower():
                found_terms.append(term)
        
        # Directly mutate the ChawanContext
        search_summary = f"Found {len(found_terms)}/{len(search_terms)} terms: {', '.join(found_terms)}"
        ctx.deps.add_action("multi_search", f"{len(search_terms)}_terms", ActionStatus.COMPLETED, search_summary)
        
        if found_terms:
            return f"✅ Multi-search: Found {len(found_terms)}/{len(search_terms)} terms: {', '.join(found_terms)}"
        else:
            return f"❌ Multi-search: No terms found from {len(search_terms)} searched"
        
    except Exception as e:
        logger.error(f"❌ Multi-search failed: {e}")
        ctx.deps.add_action("multi_search", f"{len(search_terms)}_terms", ActionStatus.FAILED, f"Search error: {str(e)}")
        return f"❌ Multi-search failed: {str(e)}"


async def dismiss_cookie_popup(ctx: RunContext[ChawanContext]) -> str:
    """Dismiss cookie consent popups - simple string return"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info("🍪 ATTEMPTING TO DISMISS COOKIE POPUP")
        
        # Get current content to check for cookie popup indicators
        content = await ctx.deps.browser.get_content()
        
        cookie_indicators = ["cookies", "cookie policy", "accept", "consent", "privacy", "gdpr"]
        has_cookie_popup = any(indicator in content.lower() for indicator in cookie_indicators)
        
        if not has_cookie_popup:
            ctx.deps.add_action("dismiss_popup", "no_popup", ActionStatus.COMPLETED, "No cookie popup detected")
            return "✅ No cookie popup detected"
        
        # Simple dismissal attempt - press Enter (common accept pattern)
        try:
            if ctx.deps.browser.process and ctx.deps.browser.process.stdin:
                ctx.deps.browser.process.stdin.write(b"\r")  # Enter key
                await ctx.deps.browser.process.stdin.drain()
                await asyncio.sleep(2)
            
            # Check if successful
            new_content = await ctx.deps.browser.get_content()
            page_info = await ctx.deps.browser.get_page_info()
            
            popup_dismissed = (
                page_info.title != "A" and 
                len(page_info.title) > 2 and
                page_info.content_length != len(content)
            )
            
            if popup_dismissed:
                ctx.deps.add_action("dismiss_popup", "success", ActionStatus.COMPLETED, "Cookie popup dismissed")
                return f"✅ Cookie popup dismissed - {page_info.title} now accessible"
            else:
                ctx.deps.add_action("dismiss_popup", "failed", ActionStatus.FAILED, "Popup still present")
                return "❌ Cookie popup still blocking access"
                
        except Exception as dismiss_error:
            ctx.deps.add_action("dismiss_popup", "error", ActionStatus.FAILED, f"Dismissal error: {str(dismiss_error)}")
            return f"❌ Cookie dismissal failed: {str(dismiss_error)}"
        
    except Exception as e:
        logger.error(f"❌ Cookie dismissal failed: {e}")
        ctx.deps.add_action("dismiss_popup", "error", ActionStatus.FAILED, f"Error: {str(e)}")
        return f"❌ Cookie popup dismissal failed: {str(e)}"


async def get_form_snapshot(ctx: RunContext[ChawanContext]) -> str:
    """Get current form data snapshot before submission - simple string return"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info("📸 CAPTURING FORM SNAPSHOT")
        
        # Get current page content to analyze form fields
        content = await ctx.deps.browser.get_content()
        
        # Basic form analysis
        form_elements = 0
        for line in content.split('\n'):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ["input", "field", "form", "submit"]):
                form_elements += 1
        
        # Directly mutate the ChawanContext
        ctx.deps.add_action("form_snapshot", "capture", ActionStatus.COMPLETED, f"Captured form with {form_elements} elements")
        
        if form_elements > 0:
            return f"✅ Form snapshot captured - {form_elements} form elements detected"
        else:
            return "⚠️ Form snapshot captured - No clear form elements detected"
        
    except Exception as e:
        logger.error(f"❌ Form snapshot failed: {e}")
        ctx.deps.add_action("form_snapshot", "error", ActionStatus.FAILED, f"Snapshot error: {str(e)}")
        return f"❌ Form snapshot failed: {str(e)}"


async def detect_form_fields(ctx: RunContext[ChawanContext]) -> str:
    """Detect and analyze form fields on current page - simple string return"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info("🔍 ANALYZING FORM FIELDS")
        
        content = await ctx.deps.browser.get_content()
        page_info = await ctx.deps.browser.get_page_info()
        
        # Basic form field detection
        detected_fields = []
        field_patterns = {
            "name": ["name", "full name", "first name", "last name"],
            "email": ["email", "e-mail", "mail address"],
            "phone": ["phone", "telephone", "mobile", "cell"],
            "address": ["address", "street", "city", "zip", "postal"],
            "company": ["company", "organization", "business"],
            "message": ["message", "comment", "note", "description"]
        }
        
        content_lower = content.lower()
        for field_type, patterns in field_patterns.items():
            for pattern in patterns:
                if pattern in content_lower:
                    detected_fields.append(field_type)
                    break
        
        # Directly mutate the ChawanContext
        detection_summary = f"Detected {len(detected_fields)} field types: {', '.join(detected_fields)}"
        ctx.deps.add_action("detect_fields", f"{len(detected_fields)}_fields", ActionStatus.COMPLETED, detection_summary)
        
        if detected_fields:
            return f"✅ Form analysis: Detected {len(detected_fields)} field types: {', '.join(detected_fields)}"
        else:
            return "⚠️ Form analysis: No clear form field patterns detected"
        
    except Exception as e:
        logger.error(f"❌ Form field detection failed: {e}")
        ctx.deps.add_action("detect_fields", "error", ActionStatus.FAILED, f"Detection error: {str(e)}")
        return f"❌ Form field detection failed: {str(e)}"


# Advanced tools - keeping a few enhanced ones but with simple returns
async def fill_form_bulk(ctx: RunContext[ChawanContext], form_data: Dict[str, str]) -> str:
    """Fill multiple form fields in a single action - simple string return"""
    try:
        if not ctx.deps.browser:
            return "❌ Browser session not initialized"

        logger.info(f"📋 Bulk filling {len(form_data)} fields")
        
        filled_count = 0
        failed_count = 0
        
        for field_desc, value in form_data.items():
            try:
                success = await ctx.deps.browser.fill_input(value)
                if success:
                    filled_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Error filling {field_desc}: {e}")
        
        # Directly mutate ChawanContext
        ctx.deps.add_action("fill_form_bulk", f"{len(form_data)}_fields", 
                          ActionStatus.COMPLETED if filled_count > failed_count else ActionStatus.FAILED,
                          f"Bulk filled {filled_count}/{len(form_data)} fields")
        
        if failed_count == 0:
            return f"✅ All {filled_count} fields filled successfully"
        else:
            return f"⚠️ Filled {filled_count}/{len(form_data)} fields ({failed_count} failed)"
        
    except Exception as e:
        logger.error(f"❌ Bulk form filling failed: {e}")
        ctx.deps.add_action("fill_form_bulk", "bulk_fill", ActionStatus.FAILED, f"Bulk fill error: {str(e)}")
        return f"❌ Bulk form filling failed: {str(e)}"


def create_chawan_instructions(ctx: RunContext[ChawanContext]) -> str:
    """Generate dynamic memory-aware instructions - JSON dump of ChawanContext"""
    context = ctx.deps
    
    # Build memory summary from ChawanContext state
    memory_sections = []
    
    if context.objective:
        memory_sections.append(f"🎯 OBJECTIVE: {context.objective}")
    
    # Recent actions from knowledge graph
    if context.actions:
        recent_actions = context.actions[-5:]  # Last 5 actions
        actions_text = "\n".join([f"  - {action.action_type}: {action.target} ({action.status})" for action in recent_actions])
        memory_sections.append(f"""
📋 RECENT ACTIONS ({len(context.actions)} total):
{actions_text}
⚠️  Don't repeat these exact actions!""")
    
    # Pages visited from knowledge graph
    if context.pages:
        pages_text = "\n".join([f"  - {page.title} ({page.url})" for page in context.pages[-3:]])
        memory_sections.append(f"""
📖 PAGES VISITED ({len(context.pages)} total):
{pages_text}""")
    
    # Progress tracking
    progress_section = f"""
📊 PROGRESS: {context.action_count}/{context.max_actions} actions used
⏱️  Actions remaining: {context.max_actions - context.action_count}"""
    memory_sections.append(progress_section)
    
    # Show browsing history with stored content for agent memory
    browsing_history = ""
    try:
        browsing_history = f"\n--- BROWSING HISTORY WITH STORED CONTENT ---\n{context.render_browsing_history()}\n"
    except Exception as e:
        logger.error(f"❌ Error rendering browsing history: {e}")
        # Fallback to JSON if browsing history fails
        try:
            browsing_history = f"\n--- CHAWAN CONTEXT KNOWLEDGE GRAPH ---\n{context.render_state()}\n"
        except Exception as e2:
            logger.error(f"❌ Error serializing ChawanContext: {e2}")
    
    return (
        "\n".join(memory_sections) + browsing_history + 
        """

🛠️ AVAILABLE TOOLS (Simple Returns, Direct Context Mutation):
1. navigate_to(url) - Navigate to URL ✅/❌
2. click_link_by_index(link_index) - Click numbered link ✅/❌
3. scroll_page(direction, n) - Scroll to see more content ✅/❌
4. fill_input(text) - Fill single input field ✅/❌
5. fill_form_bulk(form_data) - Fill multiple fields at once ✅/❌
6. submit_form() - Submit forms ✅/❌
7. get_current_url() - Get current page URL

💡 STRATEGY:
- Use your ChawanContext memory to avoid repeating actions
- All tools return simple ✅/❌ status messages
- Full browsing state is tracked in the knowledge graph
- Build on previous actions and discoveries
- Be efficient with remaining actions"""
    )


# Export refactored tools - 100% API compatible with original
__all__ = [
    # Core navigation tools
    "navigate_to",
    "click_link_by_index",
    "scroll_page",
    "get_current_url",
    # Enhanced navigation with search (focus content, reduce overload) 
    "navigate_to_with_search",
    "multi_search_page",
    # Basic form tools
    "fill_input",
    "submit_form",
    # Enhanced form tools (based on agent feedback)
    "fill_form_bulk",
    "get_form_snapshot",
    "detect_form_fields",
    # Page access tools
    "dismiss_cookie_popup",
    # Context and utilities
    "ChawanContext",
    "create_chawan_instructions",
    # New Pydantic models for dependency-as-graph pattern
    "BrowseAction",
    "PageState", 
    "ActionStatus",
]