"""
Flexible Scrape Agent - Prompt-based extraction without predefined structure

This agent:
1. Takes HTML content and a natural language prompt
2. Analyzes what's available on the page
3. Generates a dynamic data structure based on what it finds
4. Returns JSON with whatever relevant data it discovers
5. No need to predefine Pydantic models!

Much more flexible and realistic for real-world scraping.
"""

from typing import Any, Dict, List, Optional, Union

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


class FlexibleExtractionResult(BaseModel):
    """Dynamic result that can contain any discovered data"""
    
    data: Dict[str, Any] = Field(description="Extracted data in flexible JSON format")
    summary: str = Field(description="Brief summary of what was found")
    fields_found: List[str] = Field(default_factory=list, description="List of data fields discovered")
    confidence: float = Field(default=0.8, description="Confidence in extraction quality", ge=0.0, le=1.0)


class FlexibleScrapeContext(BaseModel):
    """Context for flexible scraping"""
    
    soup: Any = Field(description="BeautifulSoup object", exclude=True)
    html_preview: str = Field(description="Preview of HTML content")
    extraction_prompt: str = Field(description="What the user wants to extract")
    
    # Results tracking
    attempts: int = Field(default=0)
    last_error: str = Field(default="")
    success: bool = Field(default=False)
    extracted_result: Optional[FlexibleExtractionResult] = Field(default=None)


# Create the flexible scrape agent
flexible_scrape_agent = Agent[FlexibleExtractionResult, FlexibleScrapeContext](
    "openai:gpt-4o",
    output_type=FlexibleExtractionResult,
    system_prompt="""You are a flexible web scraping agent. Your job is to:

1. ANALYZE the HTML content to understand what data is available
2. DETERMINE what data is relevant to the user's extraction prompt
3. EXTRACT that data using CSS selectors in a flexible JSON structure
4. RETURN a FlexibleExtractionResult with whatever you found

KEY PRINCIPLES:
• Don't force a predefined structure - adapt to what's actually on the page
• Extract whatever is relevant to the prompt, even if it's not exactly what was asked
• Use descriptive field names based on the content you find
• Handle missing data gracefully - just don't include those fields
• Prefer finding SOMETHING useful over failing completely

WORKFLOW:
1. Use analyze_page_content to understand the HTML structure
2. Use extract_flexible_data to extract relevant information
3. Return a FlexibleExtractionResult with your findings

Be adaptable and practical - extract what you can find!"""
)


@flexible_scrape_agent.tool
async def analyze_page_content(ctx: RunContext[FlexibleScrapeContext]) -> str:
    """
    Analyze the HTML content to understand what data is available.
    
    Returns:
        Analysis of the page structure and available data
    """
    if not ctx.deps.soup:
        return "No HTML content available to analyze"
    
    analysis = []
    analysis.append(f"EXTRACTION GOAL: {ctx.deps.extraction_prompt}")
    analysis.append(f"HTML PREVIEW: {ctx.deps.html_preview}")
    
    # Get page structure
    title = ctx.deps.soup.find('title')
    if title:
        analysis.append(f"Page Title: {title.get_text(strip=True)}")
    
    # Find main content areas
    headers = ctx.deps.soup.find_all(['h1', 'h2', 'h3', 'h4'])[:8]
    if headers:
        analysis.append("Headers found:")
        for i, header in enumerate(headers, 1):
            text = header.get_text(strip=True)[:100]
            analysis.append(f"  {i}. {header.name}: {text}")
    
    # Find structured content
    lists = ctx.deps.soup.find_all(['ul', 'ol'])
    if lists:
        analysis.append(f"Found {len(lists)} lists with structured content")
    
    # Find forms and inputs
    forms = ctx.deps.soup.find_all('form')
    inputs = ctx.deps.soup.find_all('input')
    if forms or inputs:
        analysis.append(f"Interactive elements: {len(forms)} forms, {len(inputs)} inputs")
    
    # Find tables
    tables = ctx.deps.soup.find_all('table')
    if tables:
        analysis.append(f"Found {len(tables)} data tables")
    
    # Find links
    links = ctx.deps.soup.find_all('a', href=True)[:5]
    if links:
        analysis.append("Sample links:")
        for i, link in enumerate(links, 1):
            text = link.get_text(strip=True)[:50]
            href = link.get('href')
            analysis.append(f"  {i}. {text} -> {href}")
    
    # Find images
    images = ctx.deps.soup.find_all('img')
    if images:
        analysis.append(f"Found {len(images)} images")
    
    # Find common content patterns
    articles = ctx.deps.soup.find_all('article')
    if articles:
        analysis.append(f"Found {len(articles)} article elements")
    
    sections = ctx.deps.soup.find_all('section')
    if sections:
        analysis.append(f"Found {len(sections)} section elements")
    
    # Find text content areas
    paragraphs = ctx.deps.soup.find_all('p')
    if paragraphs:
        analysis.append(f"Found {len(paragraphs)} paragraphs of text content")
    
    return "\n".join(analysis)


@flexible_scrape_agent.tool
async def extract_flexible_data(
    ctx: RunContext[FlexibleScrapeContext],
    extraction_strategy: str
) -> str:
    """
    Extract data in a flexible JSON structure based on what's available.
    
    Args:
        extraction_strategy: Your strategy for extracting relevant data
        
    Returns:
        Result of the extraction attempt
    """
    ctx.deps.attempts += 1
    logger.info(f"Flexible extraction attempt {ctx.deps.attempts}: {extraction_strategy}")
    
    try:
        if not ctx.deps.soup:
            return "❌ No HTML content available for extraction"
        
        # Start with empty data structure
        extracted_data = {}
        fields_found = []
        
        # Extract based on common patterns and the prompt
        prompt_lower = ctx.deps.extraction_prompt.lower()
        
        # Look for titles/headlines
        if any(word in prompt_lower for word in ['title', 'headline', 'name', 'subject']):
            title_selectors = ['h1', 'h2', '.title', '.headline', '.name', 'title']
            for selector in title_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    title_text = element.get_text(strip=True)
                    if title_text:
                        extracted_data['title'] = title_text
                        fields_found.append('title')
                        break
        
        # Look for author/person information
        if any(word in prompt_lower for word in ['author', 'by', 'person', 'contact', 'name']):
            author_selectors = ['.author', '.by', '.byline', '.person', '.contact-name']
            for selector in author_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    author_text = element.get_text(strip=True)
                    if author_text:
                        extracted_data['author'] = author_text
                        fields_found.append('author')
                        break
        
        # Look for dates
        if any(word in prompt_lower for word in ['date', 'time', 'published', 'updated']):
            date_selectors = ['time', '.date', '.published', '.updated', '.timestamp']
            for selector in date_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    date_text = element.get_text(strip=True)
                    if date_text:
                        extracted_data['date'] = date_text
                        fields_found.append('date')
                        break
        
        # Look for prices
        if any(word in prompt_lower for word in ['price', 'cost', 'money', '$']):
            price_selectors = ['.price', '.cost', '.amount', '[class*="price"]', '[class*="cost"]']
            for selector in price_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    price_text = element.get_text(strip=True)
                    if price_text:
                        extracted_data['price'] = price_text
                        fields_found.append('price')
                        break
        
        # Look for descriptions/content
        if any(word in prompt_lower for word in ['description', 'content', 'text', 'summary', 'about']):
            content_selectors = ['.description', '.content', '.summary', '.about', 'p', '.text']
            for selector in content_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    content_text = element.get_text(strip=True)
                    if content_text and len(content_text) > 20:  # Ensure substantial content
                        extracted_data['description'] = content_text
                        fields_found.append('description')
                        break
        
        # Look for lists/tags
        if any(word in prompt_lower for word in ['tags', 'categories', 'list', 'items']):
            list_selectors = ['.tag', '.category', '.tags', '.categories', 'li']
            tags = []
            for selector in list_selectors:
                elements = ctx.deps.soup.select(selector)
                for element in elements[:10]:  # Limit to 10 items
                    tag_text = element.get_text(strip=True)
                    if tag_text and len(tag_text) < 50:  # Reasonable tag length
                        tags.append(tag_text)
                if tags:
                    extracted_data['tags'] = tags
                    fields_found.append('tags')
                    break
        
        # Look for links
        if any(word in prompt_lower for word in ['link', 'url', 'href']):
            links = []
            for link in ctx.deps.soup.find_all('a', href=True)[:5]:
                link_text = link.get_text(strip=True)
                link_href = link.get('href')
                if link_text and link_href:
                    links.append({'text': link_text, 'url': link_href})
            if links:
                extracted_data['links'] = links
                fields_found.append('links')
        
        # Look for contact information
        if any(word in prompt_lower for word in ['email', 'phone', 'contact']):
            # Email patterns
            email_selectors = ['.email', '[href^="mailto:"]', '[class*="email"]']
            for selector in email_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    email_text = element.get_text(strip=True) or element.get('href', '').replace('mailto:', '')
                    if '@' in email_text:
                        extracted_data['email'] = email_text
                        fields_found.append('email')
                        break
            
            # Phone patterns
            phone_selectors = ['.phone', '[href^="tel:"]', '[class*="phone"]']
            for selector in phone_selectors:
                element = ctx.deps.soup.select_one(selector)
                if element:
                    phone_text = element.get_text(strip=True) or element.get('href', '').replace('tel:', '')
                    if any(char.isdigit() for char in phone_text):
                        extracted_data['phone'] = phone_text
                        fields_found.append('phone')
                        break
        
        # If we didn't find anything specific, try to extract the most prominent content
        if not extracted_data:
            # Get the first substantial heading
            for heading in ctx.deps.soup.find_all(['h1', 'h2', 'h3']):
                text = heading.get_text(strip=True)
                if text:
                    extracted_data['main_heading'] = text
                    fields_found.append('main_heading')
                    break
            
            # Get the first substantial paragraph
            for paragraph in ctx.deps.soup.find_all('p'):
                text = paragraph.get_text(strip=True)
                if text and len(text) > 50:
                    extracted_data['main_content'] = text
                    fields_found.append('main_content')
                    break
        
        # Create the result
        if extracted_data:
            summary = f"Found {len(fields_found)} relevant fields: {', '.join(fields_found)}"
            confidence = min(len(fields_found) * 0.2, 1.0)  # Higher confidence with more fields
            
            result = FlexibleExtractionResult(
                data=extracted_data,
                summary=summary,
                fields_found=fields_found,
                confidence=confidence
            )
            
            ctx.deps.extracted_result = result
            ctx.deps.success = True
            
            logger.info(f"Flexible extraction successful: {summary}")
            return f"✅ SUCCESS! {summary}\nExtracted data: {extracted_data}"
        else:
            error_msg = "No relevant data found matching the extraction prompt"
            ctx.deps.last_error = error_msg
            return f"❌ {error_msg}"
            
    except Exception as e:
        error_msg = f"Extraction failed: {str(e)}"
        ctx.deps.last_error = error_msg
        logger.error(f"Flexible extraction error: {error_msg}")
        return f"❌ {error_msg}"


def extract_flexible_data_direct(html_content: str, prompt: str) -> Dict[str, Any]:
    """
    Direct flexible extraction without agent complexity.
    Returns whatever relevant data it can find.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    extracted_data = {}
    fields_found = []
    prompt_lower = prompt.lower()
    
    # Look for titles/headlines
    if any(word in prompt_lower for word in ['title', 'headline', 'name', 'article']):
        titles = []
        # Try multiple selectors for titles
        for selector in ['h1.title', '.title', 'h1', 'h2']:
            elements = soup.select(selector)
            for element in elements:
                title_text = element.get_text(strip=True)
                if title_text and len(title_text) > 10:  # Substantial titles
                    titles.append(title_text)
        
        if titles:
            if len(titles) == 1:
                extracted_data['title'] = titles[0]
            else:
                extracted_data['titles'] = titles
            fields_found.append('titles' if len(titles) > 1 else 'title')
    
    # Look for authors
    if any(word in prompt_lower for word in ['author', 'writer', 'by']):
        authors = []
        for selector in ['.author', '.by', '.byline', '.writer']:
            elements = soup.select(selector)
            for element in elements:
                author_text = element.get_text(strip=True)
                if author_text:
                    authors.append(author_text)
        
        if authors:
            if len(authors) == 1:
                extracted_data['author'] = authors[0]
            else:
                extracted_data['authors'] = authors
            fields_found.append('authors' if len(authors) > 1 else 'author')
    
    # Look for dates
    if any(word in prompt_lower for word in ['date', 'time', 'published']):
        dates = []
        for selector in ['time', '.date', '.published', '.timestamp']:
            elements = soup.select(selector)
            for element in elements:
                date_text = element.get_text(strip=True)
                if date_text:
                    dates.append(date_text)
        
        if dates:
            if len(dates) == 1:
                extracted_data['date'] = dates[0]
            else:
                extracted_data['dates'] = dates
            fields_found.append('dates' if len(dates) > 1 else 'date')
    
    # Look for content/descriptions
    if any(word in prompt_lower for word in ['content', 'description', 'text', 'article']):
        content_pieces = []
        for selector in ['.content p', 'article p', 'p']:
            elements = soup.select(selector)
            for element in elements:
                content_text = element.get_text(strip=True)
                if content_text and len(content_text) > 20:  # Substantial content
                    content_pieces.append(content_text)
        
        if content_pieces:
            if len(content_pieces) == 1:
                extracted_data['content'] = content_pieces[0]
            else:
                extracted_data['content_pieces'] = content_pieces
            fields_found.append('content')
    
    # Look for tags/categories
    if any(word in prompt_lower for word in ['tag', 'category', 'topic']):
        tags = []
        for selector in ['.tag', '.category', '.topic']:
            elements = soup.select(selector)
            for element in elements:
                tag_text = element.get_text(strip=True)
                if tag_text and len(tag_text) < 50:  # Reasonable tag length
                    tags.append(tag_text)
        
        if tags:
            extracted_data['tags'] = tags
            fields_found.append('tags')
    
    # Look for contact info
    if 'contact' in prompt_lower or 'email' in prompt_lower:
        contacts = {}
        
        # Email
        email_elem = soup.select_one('.email, [href^="mailto:"]')
        if email_elem:
            email_text = email_elem.get_text(strip=True) or email_elem.get('href', '').replace('mailto:', '')
            if '@' in email_text:
                contacts['email'] = email_text
        
        # Phone
        phone_elem = soup.select_one('.phone, [href^="tel:"]')
        if phone_elem:
            phone_text = phone_elem.get_text(strip=True) or phone_elem.get('href', '').replace('tel:', '')
            if any(char.isdigit() for char in phone_text):
                contacts['phone'] = phone_text
        
        if contacts:
            extracted_data['contact'] = contacts
            fields_found.append('contact')
    
    # If we didn't find anything specific, get the most prominent content
    if not extracted_data:
        # Get main heading
        main_heading = soup.select_one('h1, h2')
        if main_heading:
            extracted_data['main_heading'] = main_heading.get_text(strip=True)
            fields_found.append('main_heading')
        
        # Get first substantial paragraph
        first_para = soup.select_one('p')
        if first_para:
            para_text = first_para.get_text(strip=True)
            if len(para_text) > 30:
                extracted_data['main_content'] = para_text
                fields_found.append('main_content')
    
    # Create summary
    confidence = min(len(fields_found) * 0.25, 1.0)
    summary = f"Found {len(fields_found)} relevant fields: {', '.join(fields_found)}"
    
    return {
        'data': extracted_data,
        'summary': summary,
        'fields_found': fields_found,
        'confidence': confidence
    }


async def extract_with_flexible_agent(
    html_content: str,
    extraction_prompt: str,
    max_attempts: int = 3
) -> FlexibleExtractionResult:
    """
    Extract data using flexible extraction logic - no predefined structure needed!
    
    Args:
        html_content: HTML content to scrape
        extraction_prompt: Natural language description of what to extract
        max_attempts: Maximum number of attempts
        
    Returns:
        FlexibleExtractionResult with whatever relevant data was found
        
    Raises:
        ValueError: If extraction fails completely
    """
    logger.info(f"🚀 Starting flexible extraction: '{extraction_prompt}'")
    
    try:
        # Use direct extraction logic
        result_data = extract_flexible_data_direct(html_content, extraction_prompt)
        
        # Convert to FlexibleExtractionResult
        result = FlexibleExtractionResult(
            data=result_data['data'],
            summary=result_data['summary'],  
            fields_found=result_data['fields_found'],
            confidence=result_data['confidence']
        )
        
        logger.info(f"✅ Flexible extraction successful: {result.summary}")
        return result
            
    except Exception as e:
        error_msg = f"Direct extraction failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        raise ValueError(error_msg)


# Export the main function
__all__ = [
    "extract_with_flexible_agent",
    "flexible_scrape_agent", 
    "FlexibleExtractionResult",
    "FlexibleScrapeContext"
]