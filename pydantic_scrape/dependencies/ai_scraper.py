"""
AI Scraper Dependency - uses the BS4 script agent to extract structured data
"""

from typing import Type
from bs4 import BeautifulSoup
from pydantic import BaseModel
from loguru import logger

from ..agents.bs4_scrape_script_agent import (
    get_bs4_scrape_script_agent,
    SimpleScrapeContext
)
from .fetch import FetchResult


class AiScraperDependency:
    """
    Dependency that uses AI to extract structured data from HTML.
    
    Takes FetchResult and Pydantic model type, returns populated model instance.
    No caching - just direct AI extraction for maximum flexibility.
    """
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
    
    async def extract_data(
        self,
        fetch_result: FetchResult,
        output_type: Type[BaseModel],
        extraction_prompt: str
    ) -> BaseModel:
        """
        Use AI to extract structured data from HTML.
        
        Args:
            fetch_result: FetchResult containing HTML content
            output_type: Pydantic model to extract into
            extraction_prompt: What to extract
            
        Returns:
            Populated instance of output_type
        """
        if fetch_result.error or not fetch_result.content:
            raise ValueError(f"Invalid fetch result: {fetch_result.error}")
        
        # Create soup from HTML
        soup = BeautifulSoup(fetch_result.content, 'html.parser')
        
        # Set up context for the agent
        context = SimpleScrapeContext(
            current_soup=soup,
            target_output_type=output_type
        )
        
        logger.info(f"AiScraperDependency: Extracting {output_type.__name__} from {fetch_result.url}")
        
        # Get and run the agent
        agent = get_bs4_scrape_script_agent()
        result = await agent.run(extraction_prompt, deps=context)
        
        if result.output and context.last_result:
            logger.info(f"AiScraperDependency: Successfully extracted {output_type.__name__}")
            return context.last_result
        else:
            error_msg = f"Extraction failed. Last error: {context.last_error}"
            logger.error(f"AiScraperDependency: {error_msg}")
            raise ValueError(error_msg)
    
    def extract_data_sync(
        self,
        fetch_result: FetchResult,
        output_type: Type[BaseModel],
        extraction_prompt: str
    ) -> BaseModel:
        """Synchronous version of extract_data"""
        if fetch_result.error or not fetch_result.content:
            raise ValueError(f"Invalid fetch result: {fetch_result.error}")
        
        # Create soup from HTML
        soup = BeautifulSoup(fetch_result.content, 'html.parser')
        
        # Set up context for the agent
        context = SimpleScrapeContext(
            current_soup=soup,
            target_output_type=output_type
        )
        
        logger.info(f"AiScraperDependency: Extracting {output_type.__name__} from {fetch_result.url}")
        
        # Get and run the agent synchronously
        agent = get_bs4_scrape_script_agent()
        result = agent.run_sync(extraction_prompt, deps=context)
        
        if result.output and context.last_result:
            logger.info(f"AiScraperDependency: Successfully extracted {output_type.__name__}")
            return context.last_result
        else:
            error_msg = f"Extraction failed. Last error: {context.last_error}"
            logger.error(f"AiScraperDependency: {error_msg}")
            raise ValueError(error_msg)