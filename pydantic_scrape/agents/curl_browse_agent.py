"""
Curl-based Browse Agent

Fast, lightweight browsing using curl + terminal browsers (w3m/lynx).
This approach is much faster than full browser automation and can handle
basic HTML rendering and content extraction.

Features:
- Uses curl for HTTP requests with user-agent spoofing
- Terminal browsers (w3m, lynx) for HTML-to-text conversion
- Much faster than full browser automation
- Can handle basic authentication
- Supports various HTTP methods and headers
"""

import asyncio
import subprocess
import tempfile
from typing import List, Optional
import re

from bs4 import BeautifulSoup
from loguru import logger
from markitdown import MarkItDown
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext


class CurlBrowseTask(BaseModel):
    """Task specification for curl-based browsing"""
    url: str
    brief: str
    method: str = "GET"
    headers: dict = {}
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class CurlContext(BaseModel):
    """Context for curl browsing session"""
    task: CurlBrowseTask
    raw_html: str = ""
    rendered_text: str = ""


class CurlBrowseAgent:
    """Fast browse agent using curl + terminal browser"""

    def __init__(self, terminal_browser: str = "w3m", timeout: int = 10):
        self.terminal_browser = terminal_browser  # w3m, lynx, or links
        self.timeout = timeout
        self.md_converter = MarkItDown()
        
        # Create the browse agent
        self.agent = Agent[str, CurlContext](
            "openai:gpt-4o",
            deps_type=CurlContext,
            system_prompt=f"""You are a fast web browsing agent using curl + {terminal_browser}.

Your tools:
- fetch_page(): Get raw HTML content using curl
- render_text(): Convert HTML to readable text using {terminal_browser}
- get_clean_content(): Get cleaned markdown content
- extract_links(): Extract all links from the page
- extract_forms(): Find forms and their fields

You are very fast and lightweight compared to full browser automation.
Focus on extracting the requested information efficiently.
Return detailed results about what you found.""",
        )
        
        # Add tools
        self.agent.tool(self.fetch_page)
        self.agent.tool(self.render_text)
        self.agent.tool(self.get_clean_content)
        self.agent.tool(self.extract_links)
        self.agent.tool(self.extract_forms)

    async def fetch_page(self, ctx: RunContext[CurlContext]) -> str:
        """Fetch page content using curl"""
        try:
            task = ctx.deps.task
            
            # Build curl command
            cmd = [
                "curl",
                "-s",  # Silent
                "--max-time", str(self.timeout),
                "--user-agent", task.user_agent,
                "-L",  # Follow redirects
            ]
            
            # Add custom headers
            for key, value in task.headers.items():
                cmd.extend(["-H", f"{key}: {value}"])
            
            # Add method if not GET
            if task.method != "GET":
                cmd.extend(["-X", task.method])
            
            cmd.append(task.url)
            
            logger.info(f"🌐 Fetching {task.url} with curl")
            
            # Execute curl
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                return f"Curl failed: {error_msg}"
            
            html_content = stdout.decode('utf-8', errors='ignore')
            ctx.deps.raw_html = html_content
            
            logger.info(f"✅ Fetched {len(html_content)} bytes from {task.url}")
            return f"Successfully fetched {len(html_content)} bytes of HTML content"
            
        except Exception as e:
            return f"Failed to fetch page: {str(e)}"

    async def render_text(self, ctx: RunContext[CurlContext]) -> str:
        """Render HTML to text using terminal browser"""
        try:
            if not ctx.deps.raw_html:
                return "No HTML content available. Use fetch_page() first."
            
            # Write HTML to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(ctx.deps.raw_html)
                temp_file = f.name
            
            # Build terminal browser command
            if self.terminal_browser == "w3m":
                cmd = ["w3m", "-T", "text/html", "-dump", temp_file]
            elif self.terminal_browser == "lynx":
                cmd = ["lynx", "-dump", "-nolist", temp_file]
            elif self.terminal_browser == "links":
                cmd = ["links", "-dump", temp_file]
            else:
                return f"Unsupported terminal browser: {self.terminal_browser}"
            
            logger.info(f"🖥️ Rendering HTML with {self.terminal_browser}")
            
            # Execute terminal browser
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Clean up temp file
            import os
            try:
                os.unlink(temp_file)
            except:
                pass
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                return f"Terminal browser failed: {error_msg}"
            
            rendered_text = stdout.decode('utf-8', errors='ignore')
            ctx.deps.rendered_text = rendered_text
            
            # Limit size
            if len(rendered_text) > 4000:
                rendered_text = rendered_text[:4000] + "\n\n... [content truncated]"
            
            logger.info(f"✅ Rendered {len(rendered_text)} characters of text")
            return rendered_text
            
        except Exception as e:
            return f"Failed to render HTML: {str(e)}"

    async def get_clean_content(self, ctx: RunContext[CurlContext]) -> str:
        """Get cleaned markdown content"""
        try:
            if not ctx.deps.raw_html:
                return "No HTML content available. Use fetch_page() first."
            
            # Clean HTML with BeautifulSoup
            soup = BeautifulSoup(ctx.deps.raw_html, "lxml")
            
            # Remove noise elements
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
            
            # Limit size
            if len(markdown_content) > 4000:
                markdown_content = markdown_content[:4000] + "\n\n... [content truncated]"
            
            return markdown_content
            
        except Exception as e:
            return f"Failed to get clean content: {str(e)}"

    async def extract_links(self, ctx: RunContext[CurlContext]) -> str:
        """Extract all links from the page"""
        try:
            if not ctx.deps.raw_html:
                return "No HTML content available. Use fetch_page() first."
            
            soup = BeautifulSoup(ctx.deps.raw_html, "lxml")
            links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                if href and not href.startswith('#'):
                    links.append(f"- {text}: {href}")
            
            if not links:
                return "No links found on the page"
            
            # Limit to first 20 links
            if len(links) > 20:
                links = links[:20]
                links.append("... [more links truncated]")
            
            return "\n".join(links)
            
        except Exception as e:
            return f"Failed to extract links: {str(e)}"

    async def extract_forms(self, ctx: RunContext[CurlContext]) -> str:
        """Extract forms and their fields"""
        try:
            if not ctx.deps.raw_html:
                return "No HTML content available. Use fetch_page() first."
            
            soup = BeautifulSoup(ctx.deps.raw_html, "lxml")
            forms = []
            
            for i, form in enumerate(soup.find_all('form'), 1):
                action = form.get('action', 'No action')
                method = form.get('method', 'GET').upper()
                
                form_info = [f"Form {i}: {method} {action}"]
                
                # Extract input fields
                for input_field in form.find_all(['input', 'textarea', 'select']):
                    field_type = input_field.get('type', input_field.name)
                    field_name = input_field.get('name', 'unnamed')
                    placeholder = input_field.get('placeholder', '')
                    
                    field_info = f"  - {field_name} ({field_type})"
                    if placeholder:
                        field_info += f": {placeholder}"
                    
                    form_info.append(field_info)
                
                forms.append("\n".join(form_info))
            
            if not forms:
                return "No forms found on the page"
            
            return "\n\n".join(forms)
            
        except Exception as e:
            return f"Failed to extract forms: {str(e)}"

    async def browse_site(self, task: CurlBrowseTask) -> str:
        """Browse a single site using curl + terminal browser"""
        try:
            logger.info(f"🚀 Starting curl browse: {task.brief} -> {task.url}")

            # Create context
            context = CurlContext(task=task)

            # Execute browsing task
            instruction = f"You need to browse {task.url}. {task.brief}"
            result = await self.agent.run(instruction, deps=context)

            logger.info(f"✅ Completed curl browsing {task.url}")
            return str(result.output)

        except Exception as e:
            import traceback
            error_msg = f"Failed curl browsing {task.url}: {str(e)}"
            full_traceback = traceback.format_exc()
            logger.error(f"❌ {error_msg}\nFull traceback:\n{full_traceback}")
            return f"{error_msg}\nTraceback: {full_traceback}"


# Convenience function for parallel curl browsing
async def browse_sites_curl(tasks: List[CurlBrowseTask], terminal_browser: str = "w3m", timeout: int = 10) -> str:
    """
    Browse multiple sites using curl + terminal browser in parallel.

    Args:
        tasks: List of CurlBrowseTask objects
        terminal_browser: Terminal browser to use (w3m, lynx, links)
        timeout: Timeout in seconds for curl requests

    Returns:
        Combined results from all browsing sessions
    """
    if not tasks:
        return "No browsing tasks provided"

    logger.info(f"🚀 Starting {len(tasks)} curl browse sessions")

    async def run_curl_agent(task: CurlBrowseTask) -> tuple[str, str]:
        """Run a single curl browse agent"""
        agent = CurlBrowseAgent(terminal_browser=terminal_browser, timeout=timeout)
        result = await agent.browse_site(task)
        return task.url, result

    try:
        # Execute all agents in parallel
        results = await asyncio.gather(
            *[run_curl_agent(task) for task in tasks]
        )

        # Combine results
        combined_results = []
        for url, result in results:
            combined_results.append(f"=== {url} ===\n{result}\n")

        final_result = "\n".join(combined_results)
        logger.info(f"✅ Completed {len(tasks)} curl browse sessions")
        return final_result
        
    except Exception as e:
        logger.error(f"❌ Curl browse sessions failed: {e}")
        return f"Failed to execute curl browse sessions: {str(e)}"


# Export main functions
__all__ = ["browse_sites_curl", "CurlBrowseAgent", "CurlBrowseTask"]