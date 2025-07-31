"""
Standalone Browse Agent - Zendriver-based web browsing with parallel tabs.

This agent handles all browser interactions: navigate, get content, click, type, etc.
Takes a list of BrowseTask objects and returns combined results.
"""

import asyncio
from typing import List

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext


class BrowseTask(BaseModel):
    """Single browse task specification"""

    url: str
    brief: str


class BrowseContext(BaseModel):
    """Context for browse agent - holds browser instance and current page"""

    browser: object = None
    page: object = None
    headless: bool = False


class BrowseAgent:
    """Standalone agent for web browsing with Zendriver"""

    def __init__(self, headless: bool = False):
        self.headless = headless

        # Create the browse agent with browser tools
        self.agent = Agent[str, BrowseContext](
            "openai:gpt-4o",
            deps_type=BrowseContext,
            system_prompt="""You are a web browsing agent with these tools:

NAVIGATION TOOLS:
- navigate(url): Navigate to a new URL
- get_content(): Get page visible text content (quick)
- get_simplified_content(): Get clean, structured content with forms (RECOMMENDED)
- wait_and_get_content(): Wait longer and get page content (for complex pages)
- get_title(): Get page title

INTERACTION TOOLS:
- click(selector): Click elements by CSS selector
- type_text(selector, text): Type into input fields
- dismiss_popups(): Dismiss cookie banners and popups (use first!)
- get_form_info(): Get detailed form structure and field information

WORKFLOW RECOMMENDATIONS:
1. ALWAYS start with dismiss_popups() to clear cookie banners
2. Use get_simplified_content() for clean, structured page content
3. Use get_form_info() to understand form structure before filling
4. Use type_text() with exact field names/IDs from form info
5. Use click() to submit forms or navigate

IMPORTANT: 
- You start on the target page already loaded
- Always dismiss popups first to clear the view
- Use simplified content for easier parsing
- Get form info before attempting to fill forms
- Return detailed results of your actions""",
        )

        # Add tool decorators
        self.agent.tool(self._navigate)
        self.agent.tool(self._get_content)
        self.agent.tool(self._get_simplified_content)
        self.agent.tool(self._get_title)
        self.agent.tool(self._click)
        self.agent.tool(self._type_text)
        self.agent.tool(self._wait_and_get_content)
        self.agent.tool(self._dismiss_popups)
        self.agent.tool(self._get_form_info)

    async def _navigate(self, ctx: RunContext[BrowseContext], url: str) -> str:
        """Navigate to a new URL"""
        try:
            ctx.deps.page = await ctx.deps.browser.get(url, new_tab=True)
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Failed to navigate: {str(e)}"

    async def _get_content(self, ctx: RunContext[BrowseContext]) -> str:
        """Get page visible text content"""
        try:
            # Wait for page to load and render
            await asyncio.sleep(2)  # Wait 2 seconds for JS to load

            # Get visible text content instead of raw HTML
            content = await ctx.deps.page.evaluate(
                "document.body.innerText || document.body.textContent || ''"
            )

            if not content or len(content.strip()) < 50:
                # Fallback to HTML if no text content
                html_content = await ctx.deps.page.get_content()
                # Extract text from HTML more aggressively
                import re

                text_content = re.sub(r"<[^>]+>", "", html_content)
                text_content = re.sub(r"\s+", " ", text_content).strip()
                content = text_content

            if len(content) > 5000:
                content = content[:5000] + "... [content truncated]"
            return content
        except Exception as e:
            return f"Failed to get content: {str(e)}"

    async def _get_title(self, ctx: RunContext[BrowseContext]) -> str:
        """Get page title"""
        try:
            title = await ctx.deps.page.evaluate("document.title")
            return str(title)
        except Exception as e:
            return f"Failed to get title: {str(e)}"

    async def _click(self, ctx: RunContext[BrowseContext], selector: str) -> str:
        """Click elements by CSS selector"""
        try:
            element = await ctx.deps.page.select(selector)
            if element:
                await element.click()
                return f"Successfully clicked {selector}"
            else:
                return f"Element not found: {selector}"
        except Exception as e:
            return f"Failed to click {selector}: {str(e)}"

    async def _type_text(
        self, ctx: RunContext[BrowseContext], selector: str, text: str
    ) -> str:
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

    async def _wait_and_get_content(self, ctx: RunContext[BrowseContext]) -> str:
        """Wait for page to fully load and get content"""
        try:
            # Wait longer for complex pages
            await asyncio.sleep(5)
            return await self._get_content(ctx)
        except Exception as e:
            return f"Failed to wait and get content: {str(e)}"

    async def _get_simplified_content(self, ctx: RunContext[BrowseContext]) -> str:
        """Get simplified, structured content that's easier for agents to parse"""
        try:
            # First dismiss any popups
            await self._dismiss_popups(ctx)

            # Wait for content to load
            await asyncio.sleep(2)

            # Get simplified content by extracting key elements
            content_script = """
            // Remove common popup/overlay elements
            const popups = document.querySelectorAll('[class*="popup"], [class*="modal"], [class*="overlay"], [class*="cookie"], [id*="cookie"], [class*="banner"]');
            popups.forEach(el => el.remove());
            
            // Extract main content areas
            const mainSelectors = ['main', '[role="main"]', '.main', '#main', '.content', '#content', 'article', '.article'];
            let mainContent = '';
            
            for (const selector of mainSelectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    mainContent = elements[0].innerText || elements[0].textContent || '';
                    if (mainContent.length > 100) break;
                }
            }
            
            // If no main content found, get body but filter out nav/footer
            if (!mainContent || mainContent.length < 100) {
                const excludeSelectors = ['nav', 'header', 'footer', '.nav', '.header', '.footer', '[role="navigation"]'];
                const body = document.body.cloneNode(true);
                
                excludeSelectors.forEach(selector => {
                    const elements = body.querySelectorAll(selector);
                    elements.forEach(el => el.remove());
                });
                
                mainContent = body.innerText || body.textContent || '';
            }
            
            // Extract forms
            const forms = Array.from(document.querySelectorAll('form')).map(form => {
                const inputs = Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
                    type: input.type || input.tagName.toLowerCase(),
                    name: input.name || input.id || '',
                    placeholder: input.placeholder || '',
                    required: input.required || false
                }));
                return {
                    action: form.action || '',
                    method: form.method || 'get',
                    inputs: inputs
                };
            });
            
            return {
                title: document.title || '',
                content: mainContent.substring(0, 3000),
                forms: forms
            };
            """

            result = await ctx.deps.page.evaluate(content_script)

            # Format the result nicely
            formatted = f"TITLE: {result.get('title', 'N/A')}\n\n"
            formatted += f"CONTENT:\n{result.get('content', 'No content found')}\n\n"

            forms = result.get("forms", [])
            if forms:
                formatted += "FORMS FOUND:\n"
                for i, form in enumerate(forms):
                    formatted += f"Form {i + 1}:\n"
                    formatted += f"  Action: {form.get('action', 'N/A')}\n"
                    formatted += f"  Method: {form.get('method', 'N/A')}\n"
                    formatted += "  Inputs:\n"
                    for inp in form.get("inputs", []):
                        formatted += f"    - {inp.get('type', 'unknown')} '{inp.get('name', '')}' (placeholder: '{inp.get('placeholder', '')}', required: {inp.get('required', False)})\n"
                    formatted += "\n"

            return formatted

        except Exception as e:
            return f"Failed to get simplified content: {str(e)}"

    async def _dismiss_popups(self, ctx: RunContext[BrowseContext]) -> str:
        """Dismiss common popups, cookie banners, and overlays"""
        try:
            dismiss_script = """
            // Common popup/cookie banner selectors
            const popupSelectors = [
                // Cookie banners
                '[class*="cookie"]', '[id*="cookie"]',
                '[class*="banner"]', '[id*="banner"]',
                '[class*="consent"]', '[id*="consent"]',
                '[class*="gdpr"]', '[id*="gdpr"]',
                
                // Generic popups/modals
                '[class*="popup"]', '[id*="popup"]',
                '[class*="modal"]', '[id*="modal"]',
                '[class*="overlay"]', '[id*="overlay"]',
                '[class*="dialog"]', '[id*="dialog"]',
                
                // Common button texts for dismissal
                'button[aria-label*="close"]',
                'button[aria-label*="dismiss"]',
                '[data-dismiss]',
                '.close', '.dismiss'
            ];
            
            let dismissed = 0;
            
            // Try to click dismiss buttons first
            const dismissButtons = document.querySelectorAll('button, a, span');
            for (const btn of dismissButtons) {
                const text = (btn.innerText || btn.textContent || '').toLowerCase();
                if (text.includes('accept') || text.includes('ok') || text.includes('close') || 
                    text.includes('dismiss') || text.includes('×') || text.includes('got it')) {
                    try {
                        btn.click();
                        dismissed++;
                        break; // Only click one dismiss button
                    } catch (e) {}
                }
            }
            
            // Remove popup elements entirely
            for (const selector of popupSelectors) {
                const elements = document.querySelectorAll(selector);
                elements.forEach(el => {
                    // Check if it looks like a popup (fixed position, high z-index, etc.)
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' || style.zIndex > 1000 || 
                        el.classList.toString().includes('popup') || 
                        el.classList.toString().includes('modal') ||
                        el.classList.toString().includes('cookie')) {
                        el.remove();
                        dismissed++;
                    }
                });
            }
            
            return dismissed;
            """

            dismissed_count = await ctx.deps.page.evaluate(dismiss_script)
            if dismissed_count > 0:
                await asyncio.sleep(1)  # Wait for any animations
                return f"Dismissed {dismissed_count} popup(s)/banner(s)"
            else:
                return "No popups found to dismiss"

        except Exception as e:
            return f"Failed to dismiss popups: {str(e)}"

    async def _get_form_info(self, ctx: RunContext[BrowseContext]) -> str:
        """Get detailed information about forms on the page"""
        try:
            form_script = """
            const forms = Array.from(document.querySelectorAll('form')).map((form, index) => {
                const inputs = Array.from(form.querySelectorAll('input, textarea, select')).map(input => {
                    const labels = document.querySelectorAll(`label[for="${input.id}"]`);
                    const parentLabel = input.closest('label');
                    let label = '';
                    
                    if (labels.length > 0) {
                        label = labels[0].innerText || labels[0].textContent || '';
                    } else if (parentLabel) {
                        label = parentLabel.innerText || parentLabel.textContent || '';
                    }
                    
                    return {
                        type: input.type || input.tagName.toLowerCase(),
                        name: input.name || input.id || '',
                        id: input.id || '',
                        placeholder: input.placeholder || '',
                        required: input.required || false,
                        label: label.trim(),
                        value: input.value || ''
                    };
                });
                
                const submitButtons = Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])'));
                
                return {
                    index: index,
                    action: form.action || window.location.href,
                    method: form.method || 'get',
                    inputs: inputs,
                    submitButtons: submitButtons.map(btn => ({
                        text: btn.innerText || btn.textContent || btn.value || 'Submit',
                        type: btn.type || 'submit'
                    }))
                };
            });
            
            return forms;
            """

            forms = await ctx.deps.page.evaluate(form_script)

            if not forms:
                return "No forms found on this page"

            result = "FORMS ON PAGE:\n\n"
            for form in forms:
                result += f"Form {form['index'] + 1}:\n"
                result += f"  Action: {form['action']}\n"
                result += f"  Method: {form['method'].upper()}\n"
                result += "  Fields:\n"

                for inp in form["inputs"]:
                    label = (
                        inp["label"]
                        or inp["placeholder"]
                        or inp["name"]
                        or "Unknown field"
                    )
                    required = " (required)" if inp["required"] else ""
                    result += f"    - {label}: {inp['type']}{required} [name='{inp['name']}', id='{inp['id']}']\n"

                if form["submitButtons"]:
                    result += "  Submit buttons:\n"
                    for btn in form["submitButtons"]:
                        result += f'    - "{btn["text"]}"\n'

                result += "\n"

            return result

        except Exception as e:
            return f"Failed to get form info: {str(e)}"

    async def browse_site(self, task: BrowseTask) -> str:
        """
        Browse a single site using Zendriver.

        Args:
            task: Single BrowseTask object with url and brief

        Returns:
            String with result from browsing session
        """
        import zendriver as zd

        browser = None
        try:
            logger.info(
                f"🌐 Starting Zendriver browser for: {task.brief} -> {task.url}"
            )

            # Create single browser instance
            browser = await zd.start(headless=self.headless)

            # Wait for browser to be fully ready
            await asyncio.sleep(1)

            # Navigate to the target URL
            page = await browser.get(task.url)

            # Wait for page to load
            await asyncio.sleep(3)  # Wait 3 seconds for initial load

            # Create context for this agent
            context = BrowseContext(browser=browser, page=page, headless=self.headless)

            # Automatically dismiss popups on page load
            try:
                await self._dismiss_popups(context)
            except Exception as e:
                logger.warning(f"Failed to auto-dismiss popups: {e}")

            # Execute the browsing task
            instruction = f"You are on {task.url}. {task.brief}"
            result = await self.agent.run(instruction, deps=context)

            logger.info(f"✅ Completed browsing {task.url}")
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
                    logger.info(f"🧹 Zendriver browser cleaned up for {task.url}")
                except Exception as e:
                    logger.error(f"⚠️  Error cleaning up browser: {e}")


# Convenience function
async def browse_sites(tasks: List[BrowseTask], headless: bool = False) -> str:
    """
    Browse multiple sites by parallelizing multiple BrowseAgent instances.

    Args:
        tasks: List of BrowseTask objects with url and brief
        headless: Whether to run browser in headless mode

    Returns:
        String with combined results from all browsing sessions
    """
    if not tasks:
        return "No browsing tasks provided"

    logger.info(f"🚀 Parallelizing {len(tasks)} BrowseAgent instances")

    async def run_single_agent(task: BrowseTask) -> tuple[str, str]:
        """Run a single BrowseAgent for one task"""
        agent = BrowseAgent(headless=headless)
        result = await agent.browse_site(task)
        return task.url, result

    # Execute all agents in parallel
    results = await asyncio.gather(*[run_single_agent(task) for task in tasks])

    # Combine results
    combined_results = []
    for url, result in results:
        combined_results.append(f"=== {url} ===\n{result}\n")

    final_result = "\n".join(combined_results)
    logger.info(f"✅ Completed parallel browsing with {len(tasks)} agents")
    return final_result


# Export the main functions and classes
__all__ = ["browse_sites", "BrowseAgent", "BrowseTask"]
