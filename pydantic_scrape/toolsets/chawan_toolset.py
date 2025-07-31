"""
Chawan Browser Toolset for Pydantic AI

A modular, reusable toolset that provides chawan browser automation capabilities.
This toolset can be registered with any Pydantic AI agent to enable web browsing.

Features:
- Navigation and content extraction
- Link clicking and form interaction
- Memory-aware action tracking
- Flexible configuration for different use cases
"""

import asyncio
from typing import Dict, List, Optional, Set

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import RunContext

# FunctionToolset may not be available - we'll register tools directly with agents
from pydantic_scrape.dependencies.chawan_browser_api import (
    ChawanBrowser,
    Direction,
    PageInfo,
)


class ChawanContext(BaseModel):
    """Context for chawan browser operations with memory tracking"""

    model_config = {"arbitrary_types_allowed": True}

    # Core browser state
    browser: Optional[ChawanBrowser] = None
    current_page_info: Optional[PageInfo] = None
    objective: Optional[str] = None
    max_actions: int = 10
    action_count: int = 0

    # Enhanced memory system
    visited_urls: Optional[List[str]] = None
    clicked_links: Optional[List[str]] = None
    actions_taken: Optional[List[str]] = None
    pages_browsed: Optional[Set[str]] = None

    def __post_init__(self):
        if self.visited_urls is None:
            self.visited_urls = []
        if self.clicked_links is None:
            self.clicked_links = []
        if self.actions_taken is None:
            self.actions_taken = []
        if self.pages_browsed is None:
            self.pages_browsed = set()

    def record_action(
        self, action_description: str, url: str = None, link_info: str = None
    ):
        """Record an action taken during browsing"""
        self.actions_taken.append(action_description)
        if url and url not in self.visited_urls:
            self.visited_urls.append(url)
        if link_info and link_info not in self.clicked_links:
            self.clicked_links.append(link_info)


# Individual tool functions that can be registered directly with agents


# Tools are defined as regular async functions with proper type hints
async def navigate_to(ctx: RunContext[ChawanContext], url: str) -> str:
    """Navigate to a specific URL and return page content with numbered links"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"< NAVIGATING TO: {url}")

        content = await ctx.deps.browser.navigate(url)

        # Get AI-friendly content with numbered links
        ai_content = await ctx.deps.browser.get_content_with_numbered_links()

        # Get page info
        ctx.deps.current_page_info = await ctx.deps.browser.get_page_info()

        # Update context and record action
        ctx.deps.action_count += 1
        page_info = ctx.deps.current_page_info
        ctx.deps.record_action(f"Navigated to {page_info.title} ({url})", url=url)

        # Track page browsed
        if page_info.title:
            ctx.deps.pages_browsed.add(page_info.title)

        logger.info(f"=� PAGE LOADED: '{page_info.title}'")
        logger.info(
            f"=� CONTENT: {page_info.content_length} chars, {page_info.line_count} lines"
        )
        logger.info(f"= LINKS FOUND: {len(page_info.links)} available")

        # Return comprehensive page summary
        page_summary = f"""
=== PAGE INFORMATION ===
Title: {page_info.title}
URL: {ctx.deps.browser.get_current_url()}
Content: {page_info.content_length} chars, {page_info.line_count} lines
Available Links: {len(page_info.links)}

=== PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}
"""

        return page_summary

    except Exception as e:
        logger.error(f"L Navigation failed: {e}")
        return f"Navigation failed: {str(e)}"


async def click_link_by_index(ctx: RunContext[ChawanContext], link_index: int) -> str:
    """Click a specific numbered link [1], [2], etc. - Most reliable navigation method"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"<� PRECISE LINK NAVIGATION: Clicking link {link_index}")

        old_url = ctx.deps.browser.get_current_url()
        content = await ctx.deps.browser.click_link_by_index(link_index)
        new_url = ctx.deps.browser.get_current_url()

        # Update context and record action
        ctx.deps.action_count += 1
        ctx.deps.record_action(
            f"Clicked link [{link_index}]: {old_url} � {new_url}",
            url=new_url,
            link_info=f"Link [{link_index}] from {old_url}",
        )

        # Get updated page info
        ctx.deps.current_page_info = await ctx.deps.browser.get_page_info()
        page_info = ctx.deps.current_page_info

        navigation_info = ""
        if old_url != new_url:
            logger.info(f"= LINK {link_index} NAVIGATION: {old_url} � {new_url}")
            navigation_info = f" Navigated from {old_url} to {new_url}\n\n"

        # Return updated page content
        page_summary = f"""{navigation_info}=== LINK {link_index} CLICK RESULT ===
New Page Title: {page_info.title}
New URL: {new_url}
Content: {page_info.content_length} chars, {page_info.line_count} lines
Available Links: {len(page_info.links)}

=== NEW PAGE CONTENT WITH NUMBERED LINKS ===
{content}
"""

        return page_summary

    except Exception as e:
        logger.error(f"L Link {link_index} click failed: {e}")
        return f"Link {link_index} click failed: {str(e)}"


async def scroll_page(
    ctx: RunContext[ChawanContext], direction: str, n: int = 1
) -> str:
    """Scroll page in specified direction and return updated content"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"=� SCROLLING: {direction} by {n} pages")

        direction_enum = Direction(direction.lower())
        success = await ctx.deps.browser.scroll_page(direction_enum, n)
        ctx.deps.action_count += 1
        ctx.deps.record_action(f"Scrolled {direction} by {n} pages")

        if success:
            # Get updated content after scroll
            content = await ctx.deps.browser.get_content()
            ctx.deps.current_page_info = await ctx.deps.browser.get_page_info()
            page_info = ctx.deps.current_page_info

            page_summary = f"""=== SCROLL RESULT ===
Scrolled: {direction} by {n} pages
Current Page: {page_info.title}
Content: {page_info.content_length} chars, {page_info.line_count} lines
Available Links: {len(page_info.links)}

=== UPDATED PAGE CONTENT ===
{content}
"""
            return page_summary
        else:
            return f"Failed to scroll page {direction}"

    except Exception as e:
        logger.error(f"L Page scroll failed: {e}")
        return f"Page scroll failed: {str(e)}"


async def fill_input(ctx: RunContext[ChawanContext], text: str) -> str:
    """Fill current input field with text"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info("=� FORM INPUT DETECTED =�")
        logger.info(f"=� Input Text: '{text}'")

        success = await ctx.deps.browser.fill_input(text)
        ctx.deps.action_count += 1
        ctx.deps.record_action(f"Filled input field with: '{text}'")

        if success:
            return f"Successfully filled input field with: {text}"
        else:
            return "Failed to fill input field"

    except Exception as e:
        logger.error(f"L Input filling failed: {e}")
        return f"Input filling failed: {str(e)}"


async def submit_form(ctx: RunContext[ChawanContext]) -> str:
    """Submit current form and return result"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        old_url = ctx.deps.browser.get_current_url()

        logger.info("=� FORM SUBMISSION =�")
        logger.info(f"=� Submitting form on: {old_url}")

        content = await ctx.deps.browser.submit_form()
        new_url = ctx.deps.browser.get_current_url()

        # Update context and record action
        ctx.deps.action_count += 1
        ctx.deps.record_action(f"Submitted form: {old_url} � {new_url}", url=new_url)

        # Get updated page info
        ctx.deps.current_page_info = await ctx.deps.browser.get_page_info()

        navigation_info = ""
        if old_url != new_url:
            navigation_info = (
                f" Form submission navigated from {old_url} to {new_url}\n\n"
            )

        return f"{navigation_info}Form submission successful. Result page:\n\n{content}"

    except Exception as e:
        logger.error(f"L Form submission failed: {e}")
        return f"Form submission failed: {str(e)}"


async def get_current_url(ctx: RunContext[ChawanContext]) -> str:
    """Get current page URL"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        url = ctx.deps.browser.get_current_url()
        return f"Current URL: {url}"

    except Exception as e:
        return f"Failed to get current URL: {str(e)}"


async def dismiss_cookie_popup(ctx: RunContext[ChawanContext]) -> str:
    """Dismiss cookie consent popups that block page access"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info("🍪 ATTEMPTING TO DISMISS COOKIE POPUP")
        
        # Get current content to check for cookie popup indicators
        content = await ctx.deps.browser.get_content()
        
        cookie_indicators = [
            "cookies", "cookie policy", "accept", "consent", 
            "privacy", "gdpr", "analytics cookie", "necessary cookies"
        ]
        
        has_cookie_popup = any(indicator in content.lower() for indicator in cookie_indicators)
        
        if not has_cookie_popup:
            return "No cookie popup detected on current page"

        # Try common cookie dismissal strategies
        dismissal_attempts = []
        
        # Strategy 1: Try pressing Escape key
        try:
            # Send escape key
            if ctx.deps.browser.process and ctx.deps.browser.process.stdin:
                ctx.deps.browser.process.stdin.write(b"\x1b")  # ESC key
                await ctx.deps.browser.process.stdin.drain()
                await asyncio.sleep(1)
                dismissal_attempts.append("Pressed ESC key")
        except Exception as e:
            dismissal_attempts.append(f"ESC key failed: {str(e)}")

        # Strategy 2: Try pressing Tab + Enter (common accept pattern)
        try:
            if ctx.deps.browser.process and ctx.deps.browser.process.stdin:
                ctx.deps.browser.process.stdin.write(b"\t\r")  # Tab + Enter
                await ctx.deps.browser.process.stdin.drain()
                await asyncio.sleep(1)
                dismissal_attempts.append("Tried Tab+Enter")
        except Exception as e:
            dismissal_attempts.append(f"Tab+Enter failed: {str(e)}")

        # Strategy 3: Try pressing Enter (default accept)
        try:
            if ctx.deps.browser.process and ctx.deps.browser.process.stdin:
                ctx.deps.browser.process.stdin.write(b"\r")  # Enter
                await ctx.deps.browser.process.stdin.drain()
                await asyncio.sleep(2)
                dismissal_attempts.append("Pressed Enter")
        except Exception as e:
            dismissal_attempts.append(f"Enter failed: {str(e)}")

        # Check if popup was dismissed by getting fresh content
        new_content = await ctx.deps.browser.get_content()
        page_info = await ctx.deps.browser.get_page_info()
        
        ctx.deps.action_count += 1
        ctx.deps.record_action("Attempted to dismiss cookie popup")

        # Check if we have a real page title now (not just "A")
        popup_dismissed = (
            page_info.title != "A" and 
            len(page_info.title) > 2 and
            page_info.content_length != len(content)  # Content changed
        )

        result = f"""🍪 COOKIE POPUP DISMISSAL ATTEMPT

Popup detected: {has_cookie_popup}
Dismissal strategies tried: {len(dismissal_attempts)}

Attempts made:
{chr(10).join([f"  • {attempt}" for attempt in dismissal_attempts])}

Result:
  • New page title: {page_info.title}
  • Content length: {page_info.content_length} chars
  • Available links: {len(page_info.links)}
  • Popup dismissed: {'✅ YES' if popup_dismissed else '❌ NO'}

{f'✅ Success! Page now accessible.' if popup_dismissed else '❌ Cookie popup may still be blocking access. Try refreshing or using different navigation.'}"""

        return result

    except Exception as e:
        logger.error(f"🍪 Cookie dismissal failed: {e}")
        return f"Cookie popup dismissal failed: {str(e)}"


# ENHANCED TOOLS - Based on Agent Feedback


async def navigate_to_with_search(
    ctx: RunContext[ChawanContext], url: str, search_terms: List[str] = None
) -> str:
    """Navigate to URL and optionally search for specific terms to return focused content

    Args:
        url: URL to navigate to
        search_terms: Optional list of terms to search for (returns focused results instead of full page)
                     e.g., ["contact", "email", "form", "@"] for contact info

    Returns:
        Full page content if no search terms, or focused search results if search terms provided
    """
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"🌐 NAVIGATING TO: {url}")
        if search_terms:
            logger.info(f"🔍 SEARCH TERMS: {search_terms}")

        # Navigate to the page first
        content = await ctx.deps.browser.navigate(url)
        ctx.deps.current_page_info = await ctx.deps.browser.get_page_info()
        page_info = ctx.deps.current_page_info

        # With breakthrough config (scripting="app" + CSS disabled), pages load with full content
        # even with cookie popups present, so no dismissal needed!

        # Update context
        ctx.deps.action_count += 1
        ctx.deps.record_action(f"Navigated to {page_info.title} ({url})")

        if page_info.title:
            ctx.deps.pages_browsed.add(page_info.title)

        # If no search terms, return full content (existing behavior)
        if not search_terms:
            ai_content = await ctx.deps.browser.get_content_with_numbered_links()
            return f"""=== PAGE INFORMATION ===
Title: {page_info.title}
URL: {ctx.deps.browser.get_current_url()}
Content: {page_info.content_length} chars, {page_info.line_count} lines
Available Links: {len(page_info.links)}

=== PAGE CONTENT WITH NUMBERED LINKS ===
{ai_content}"""

        # FAST SEARCH WITH CONTEXT - Use optimized browser method
        logger.info(f"🎯 FAST SEARCH WITH CONTEXT: Searching for {len(search_terms)} terms")

        # Get content once and reuse for search (much faster!)
        full_content = await ctx.deps.browser.get_content()
        
        # Use the new fast search method with pre-loaded content
        search_results_dict = await ctx.deps.browser.search_with_context(
            search_terms=search_terms,
            content=full_content,  # Pass content to avoid re-fetching
            context_lines=2,  # Include 2 lines before/after matches
            max_matches_per_term=5
        )
        
        # Convert to the format expected by the rest of the function
        search_results = []
        for term, matches in search_results_dict.items():
            if matches:
                # Convert format to match existing structure
                formatted_results = []
                for match in matches:
                    formatted_results.append({
                        "line_num": match["line_num"],
                        "context": match["context"], 
                        "match": match["match_line"]
                    })
                
                search_results.append({
                    "term": term,
                    "matches": len(matches),
                    "results": formatted_results
                })

        # Format focused results
        if not search_results:
            return f"""🔍 FOCUSED SEARCH - No Results Found

Searched for: {", ".join(search_terms)}
Page: {page_info.title}
URL: {url}

💡 Try different search terms or use navigate_to() without search terms to see full content."""

        focused_content = f"""🎯 FOCUSED SEARCH RESULTS - {page_info.title}

URL: {url}
Page size: {page_info.content_length} chars (showing focused results only)
Search terms: {", ".join(search_terms)}

"""

        for result in search_results:
            focused_content += f"""
📍 TERM: "{result["term"]}" - {result["matches"]} matches found

"""
            for match in result["results"]:
                focused_content += f"""  Line {match["line_num"]}:
{match["context"]}
  ───────────────────────────

"""

        # Still get numbered links for navigation
        ai_content = await ctx.deps.browser.get_content_with_numbered_links()
        link_info = f"\n🔗 AVAILABLE LINKS: {len(page_info.links)}\n"
        if page_info.links:
            # Extract just the link summary, not full content
            link_lines = ai_content.split("\n")
            for line in link_lines:
                if "[" in line and "]" in line and "http" in line:
                    link_info += f"{line}\n"

        return focused_content + link_info

    except Exception as e:
        logger.error(f"🌐 Navigation with search failed: {e}")
        return f"Navigation with search failed: {str(e)}"


async def multi_search_page(
    ctx: RunContext[ChawanContext], search_terms: List[str]
) -> str:
    """Search current page for multiple terms and return focused results - saves actions!

    Args:
        search_terms: List of terms to search for simultaneously
                     e.g., ["contact", "email", "form", "@", "phone"] for contact info

    Returns:
        Focused search results from current page
    """
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"🔍 MULTI-SEARCH: {len(search_terms)} terms on current page")

        # Get current page content
        content = await ctx.deps.browser.get_content()
        page_info = await ctx.deps.browser.get_page_info()

        ctx.deps.action_count += 1
        ctx.deps.record_action(
            f"Multi-searched for: {', '.join(search_terms[:3])}{'...' if len(search_terms) > 3 else ''}"
        )

        search_results = []
        content_lines = content.split("\n")

        for term in search_terms:
            term_results = []
            for i, line in enumerate(content_lines):
                if term.lower() in line.lower():
                    # Include context around matches
                    context_start = max(0, i - 1)
                    context_end = min(len(content_lines), i + 2)
                    context = content_lines[context_start:context_end]
                    term_results.append(
                        {
                            "line_num": i + 1,
                            "context": "\n".join(context),
                            "match": line.strip(),
                        }
                    )

            if term_results:
                search_results.append(
                    {
                        "term": term,
                        "matches": len(term_results),
                        "results": term_results[
                            :3
                        ],  # Limit to 3 matches per term for multi-search
                    }
                )

        if not search_results:
            return f"""🔍 MULTI-SEARCH - No Results Found

Searched for: {", ".join(search_terms)}
Current page: {page_info.title}
URL: {ctx.deps.browser.get_current_url()}

💡 Try scrolling or navigating to different sections of the site."""

        results_summary = f"""🎯 MULTI-SEARCH RESULTS - {page_info.title}

Found results for {len(search_results)}/{len(search_terms)} search terms:

"""

        for result in search_results:
            results_summary += f"""📍 "{result["term"]}" - {result["matches"]} matches:
"""
            for match in result["results"]:
                # Show just the matching line for multi-search (more compact)
                results_summary += f"   Line {match['line_num']}: {match['match']}\n"
            results_summary += "\n"

        return results_summary

    except Exception as e:
        logger.error(f"🔍 Multi-search failed: {e}")
        return f"Multi-search failed: {str(e)}"


# ENHANCED TOOLS - Based on Agent Feedback


async def fill_form_bulk(
    ctx: RunContext[ChawanContext], form_data: Dict[str, str]
) -> str:
    """Fill multiple form fields in a single action - saves action count!

    Args:
        form_data: Dictionary mapping field descriptions to values
                  e.g., {"name": "John Doe", "email": "john@example.com", "phone": "123-456-7890"}

    Returns:
        Summary of filled fields and any errors
    """
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info(f"🚀 BULK FORM FILLING: {len(form_data)} fields")

        filled_fields = []
        failed_fields = []

        for field_desc, value in form_data.items():
            try:
                success = await ctx.deps.browser.fill_input(value)
                if success:
                    filled_fields.append(f"{field_desc}: '{value}'")
                    logger.info(f"✅ Filled {field_desc}: '{value}'")
                else:
                    failed_fields.append(f"{field_desc}: '{value}' (failed)")
                    logger.warning(f"❌ Failed to fill {field_desc}")
            except Exception as e:
                failed_fields.append(f"{field_desc}: '{value}' (error: {str(e)})")
                logger.error(f"❌ Error filling {field_desc}: {e}")

        # Record as single action (saves action count!)
        ctx.deps.action_count += 1
        ctx.deps.record_action(
            f"Bulk filled {len(filled_fields)} fields: {', '.join([f.split(':')[0] for f in filled_fields])}"
        )

        result = f"""🎯 BULK FORM FILLING COMPLETE
        
✅ Successfully filled ({len(filled_fields)} fields):
{chr(10).join([f"  - {field}" for field in filled_fields])}"""

        if failed_fields:
            result += f"""

❌ Failed to fill ({len(failed_fields)} fields):
{chr(10).join([f"  - {field}" for field in failed_fields])}"""

        return result

    except Exception as e:
        logger.error(f"💥 Bulk form filling failed: {e}")
        return f"Bulk form filling failed: {str(e)}"


async def get_form_snapshot(ctx: RunContext[ChawanContext]) -> str:
    """Get current form data snapshot before submission - shows what will be submitted"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info("📸 CAPTURING FORM SNAPSHOT")

        # Get current page content to analyze form fields
        content = await ctx.deps.browser.get_content()

        # This is a basic implementation - in practice, you'd want to parse the HTML
        # to extract actual form field values, but for now we'll analyze the content
        form_info = []

        # Look for common form patterns in the content
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if any(
                keyword in line.lower()
                for keyword in [
                    "input",
                    "name:",
                    "email:",
                    "phone:",
                    "address:",
                    "field",
                ]
            ):
                if line and len(line) < 100:  # Reasonable form field line
                    form_info.append(line)

        ctx.deps.record_action("Captured form snapshot for review")

        snapshot = f"""📸 FORM SNAPSHOT - Current Form State:

📋 Detected Form Elements:
{chr(10).join([f"  • {info}" for info in form_info[:10]])}  # Limit to 10 items

💡 This shows the current state of the form before submission.
   Review this data to ensure accuracy before calling submit_form().

Current URL: {ctx.deps.browser.get_current_url()}"""

        return snapshot

    except Exception as e:
        logger.error(f"📸 Form snapshot failed: {e}")
        return f"Form snapshot failed: {str(e)}"


async def detect_form_fields(ctx: RunContext[ChawanContext]) -> str:
    """Detect and analyze form fields on current page - helps with bulk filling"""
    try:
        if not ctx.deps.browser:
            return "Error: Browser session not initialized"

        logger.info("🔍 ANALYZING FORM FIELDS")

        content = await ctx.deps.browser.get_content()
        page_info = await ctx.deps.browser.get_page_info()

        # Basic form field detection from content
        detected_fields = []
        field_patterns = {
            "name": ["name", "full name", "first name", "last name"],
            "email": ["email", "e-mail", "mail address"],
            "phone": ["phone", "telephone", "mobile", "cell"],
            "address": ["address", "street", "city", "zip", "postal"],
            "company": ["company", "organization", "business"],
            "message": ["message", "comment", "note", "description"],
        }

        content_lower = content.lower()

        for field_type, patterns in field_patterns.items():
            for pattern in patterns:
                if pattern in content_lower:
                    detected_fields.append(
                        f"{field_type.title()} field (pattern: '{pattern}')"
                    )
                    break

        ctx.deps.record_action(
            f"Analyzed form: found {len(detected_fields)} potential fields"
        )

        analysis = f"""🔍 FORM FIELD ANALYSIS - {page_info.title}

📋 Detected Form Fields ({len(detected_fields)}):
{chr(10).join([f"  🎯 {field}" for field in detected_fields])}

💡 Usage Tips:
  • Use fill_form_bulk() with a dictionary like:
    {{"name": "John Doe", "email": "john@example.com", "phone": "123-456-7890"}}
  • This saves actions compared to individual fill_input() calls
  • Always call get_form_snapshot() before submit_form() to verify data

Current URL: {ctx.deps.browser.get_current_url()}"""

        return analysis

    except Exception as e:
        logger.error(f"🔍 Form analysis failed: {e}")
        return f"Form field detection failed: {str(e)}"


def create_chawan_instructions(ctx: RunContext[ChawanContext]) -> str:
    """Generate dynamic memory-aware instructions for chawan browsing"""
    context = ctx.deps

    if not context.objective:
        return ""

    # Build memory summary
    memory_sections = []

    # Current objective
    memory_sections.append(f"<� CURRENT OBJECTIVE: {context.objective}")

    # Actions taken so far
    if context.actions_taken:
        recent_actions = context.actions_taken[-5:]  # Show last 5 actions
        actions_text = "\n".join([f"  - {action}" for action in recent_actions])
        memory_sections.append(f"""
= RECENT ACTIONS TAKEN ({len(context.actions_taken)} total):
{actions_text}
�  Don't repeat these exact same actions!""")
    else:
        memory_sections.append("= ACTIONS TAKEN: None yet - start with navigate_to()")

    # URLs visited
    if context.visited_urls:
        urls_list = "\n".join(
            [f"  - {url}" for url in context.visited_urls[-3:]]
        )  # Show last 3
        memory_sections.append(f"""
< RECENTLY VISITED URLs ({len(context.visited_urls)} total):
{urls_list}""")
    else:
        memory_sections.append("< VISITED URLs: None yet")

    # Links clicked
    if context.clicked_links:
        links_list = "\n".join(
            [f"  - {link}" for link in context.clicked_links[-3:]]
        )  # Show last 3
        memory_sections.append(f"""
= RECENTLY CLICKED LINKS ({len(context.clicked_links)} total):
{links_list}
�  Consider different links to explore new content!""")
    else:
        memory_sections.append("= CLICKED LINKS: None yet")

    # Progress tracking
    progress_section = f"""
=� PROGRESS: {context.action_count}/{context.max_actions} actions used
� Actions remaining: {context.max_actions - context.action_count}"""
    memory_sections.append(progress_section)

    return (
        "\n".join(memory_sections)
        + """

AVAILABLE TOOLS:
🌐 NAVIGATION & SEARCH:
1. navigate_to(url) - Navigate to URL and get FULL page content with numbered links
2. navigate_to_with_search(url, search_terms) - Navigate and get FOCUSED search results only! 🎯
3. multi_search_page(search_terms) - Search current page for multiple terms (saves actions!)
4. click_link_by_index(link_index) - Click numbered link [1], [2], etc. (MOST RELIABLE)
5. scroll_page(direction, n) - Scroll to see more content  
6. get_current_url() - Get current page URL

📝 FORM HANDLING:
7. detect_form_fields() - Analyze and detect form fields on current page
8. fill_form_bulk(form_data) - Fill multiple fields in ONE action (SAVES ACTIONS!)
9. fill_input(text) - Fill single input field (use bulk for multiple fields)
10. get_form_snapshot() - Preview form data before submission (RECOMMENDED!)
11. submit_form() - Submit forms

💡 ENHANCED WORKFLOWS:

🎯 FOCUSED CONTENT DISCOVERY:
• For contact info: navigate_to_with_search(url, ["contact", "email", "@", "phone"])
• For forms: navigate_to_with_search(url, ["form", "input", "submit", "register"])
• Multi-search current page: multi_search_page(["contact", "email", "form"])
• This returns ONLY relevant content instead of overwhelming full pages!

📝 EFFICIENT FORM HANDLING:
• detect_form_fields() → fill_form_bulk() → get_form_snapshot() → submit_form()
• Use bulk filling: fill_form_bulk({"name": "John", "email": "john@example.com"})

STRATEGY:
- Use your memory to avoid repeating actions
- Build on what you've already discovered
- Use click_link_by_index() for precise navigation
- If you've found relevant info, extract and summarize it
- If you need more info, explore new links/sections
- Be efficient with remaining actions"""
    )


# Export individual tool functions and helper functions
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
]
