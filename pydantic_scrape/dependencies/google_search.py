"""
Enhanced Google Search Interface
Provides unified, powerful search capabilities including web, shopping, images, and news.
Uses rich Pydantic models for precise AI-driven search control.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import httpx
from loguru import logger
from pydantic import BaseModel, Field


class DateRange(BaseModel):
    """Date range for search filtering"""

    period: Literal["day", "week", "month", "year"] = "month"
    count: int = Field(default=1, ge=1, le=10)

    def to_api_format(self) -> str:
        """Convert to Google API date restrict format"""
        period_map = {"day": "d", "week": "w", "month": "m", "year": "y"}
        return f"{period_map[self.period]}{self.count}"


class ShoppingFilters(BaseModel):
    """Google Shopping specific filters"""

    min_price: Optional[float] = Field(
        None, ge=0, description="Minimum price in specified currency"
    )
    max_price: Optional[float] = Field(
        None, ge=0, description="Maximum price in specified currency"
    )
    currency: str = Field("GBP", description="Currency code (GBP, USD, EUR, etc.)")
    product_condition: Optional[Literal["new", "used", "refurbished"]] = None
    merchant: Optional[str] = Field(
        None, description="Specific merchant/store to search within"
    )


class SearchRequest(BaseModel):
    """
    Comprehensive search request with rich filtering capabilities.

    This single interface provides access to all Google search types with precise control.
    Perfect for AI agents that need to perform targeted searches with specific requirements.
    """

    # Core search parameters
    query: str = Field(..., description="The search query string")
    search_type: Literal["web", "shopping", "images", "news"] = Field(
        "web",
        description="Type of search: web (general), shopping (products/prices), images, news",
    )

    # Results control
    num_results: int = Field(
        10, ge=1, le=10, description="Number of results to return (max 10)"
    )
    language: str = Field("en", description="Language code for results")
    safe_search: Literal["off", "medium", "high"] = Field(
        "medium", description="Safe search level"
    )

    # Geographic targeting
    location: Optional[str] = Field(
        None,
        description="Geographic location (e.g., 'UK', 'North West England', 'Manchester')",
    )
    country_code: Optional[str] = Field(
        None, description="Country code for targeting (e.g., 'uk', 'us', 'ca')"
    )

    # Site filtering
    site_include: Optional[List[str]] = Field(
        None,
        description="Include only results from these domains (e.g., ['amazon.co.uk', 'ebay.co.uk'])",
    )
    site_exclude: Optional[List[str]] = Field(
        None, description="Exclude results from these domains"
    )

    # Content filtering
    file_type: Optional[str] = Field(
        None, description="Restrict to specific file types (pdf, doc, xls, ppt, etc.)"
    )
    exact_terms: Optional[List[str]] = Field(
        None, description="Terms that must appear exactly in results"
    )
    exclude_terms: Optional[List[str]] = Field(
        None, description="Terms to exclude from results"
    )

    # Time filtering
    date_range: Optional[DateRange] = Field(
        None, description="Restrict results to specific time period"
    )

    # Shopping specific
    shopping_filters: Optional[ShoppingFilters] = Field(
        None, description="Filters specific to shopping/product search"
    )

    # Advanced options
    related_site: Optional[str] = Field(
        None, description="Find sites related to this URL"
    )
    link_site: Optional[str] = Field(
        None, description="Find pages that link to this URL"
    )

    def build_query_string(self) -> str:
        """Build enhanced query string with all filters"""
        query_parts = [self.query]

        # Add exact terms
        if self.exact_terms:
            for term in self.exact_terms:
                query_parts.append(f'"{term}"')

        # Add excluded terms
        if self.exclude_terms:
            for term in self.exclude_terms:
                query_parts.append(f"-{term}")

        # Add site inclusions
        if self.site_include:
            site_query = " OR ".join(f"site:{site}" for site in self.site_include)
            query_parts.append(f"({site_query})")

        # Add site exclusions
        if self.site_exclude:
            for site in self.site_exclude:
                query_parts.append(f"-site:{site}")

        # Add file type
        if self.file_type:
            query_parts.append(f"filetype:{self.file_type}")

        # Add related/link searches
        if self.related_site:
            query_parts.append(f"related:{self.related_site}")

        if self.link_site:
            query_parts.append(f"link:{self.link_site}")

        return " ".join(query_parts)


class SearchResult(BaseModel):
    """Structured search result"""

    title: str
    url: str
    snippet: str
    display_url: str
    search_type: str

    # Optional enriched data
    image: Optional[Dict[str, Any]] = None
    organization: Optional[Dict[str, Any]] = None
    rating: Optional[Dict[str, Any]] = None
    price: Optional[Dict[str, Any]] = None  # For shopping results


class SearchResults(BaseModel):
    """Complete search results with metadata"""

    results: List[SearchResult]
    total_found: int
    search_request: SearchRequest
    query_used: str
    search_time: float
    timestamp: datetime = Field(default_factory=datetime.now)


class GoogleCustomSearchClient:
    """
    Enhanced Google Custom Search Engine client with unified interface.

    Supports web, shopping, images, and news search with rich Pydantic models.
    Provides 10,000 free queries per month across all search types.
    Perfect for AI agents that need precise search control.
    """

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv(
            "CUSTOM_GOOGLE_SEARCH_API_KEY"
        )
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID") or os.getenv(
            "CUSTOM_GOOGLE_SEARCH_ID"
        )
        self.base_url = "https://www.googleapis.com/customsearch/v1"

        # Check if credentials are available
        self.enabled = bool(self.api_key and self.search_engine_id)

        if not self.enabled:
            logger.warning(
                "🚫 Enhanced Google Search not configured - missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID"
            )
        else:
            logger.info(
                "✅ Enhanced Google Search client initialized with unified interface"
            )

    async def enhanced_search(self, request: SearchRequest) -> SearchResults:
        """
        Unified search interface supporting all Google search types with rich filtering.

        This single method replaces all previous search methods and provides:
        - Web search (general results)
        - Shopping search (products, prices, reviews)
        - Image search
        - News search
        - Advanced filtering (location, sites, dates, prices, etc.)

        Args:
            request: SearchRequest with all search parameters and filters

        Returns:
            SearchResults with structured data and metadata
        """
        if not self.enabled:
            logger.warning("🚫 Enhanced Google Search not available")
            return SearchResults(
                results=[],
                total_found=0,
                search_request=request,
                query_used=request.query,
                search_time=0.0,
            )

        start_time = datetime.now()
        enhanced_query = request.build_query_string()

        # Add UK-specific terms when targeting UK to force local results
        if request.country_code == "uk" or (
            request.location
            and any(
                term in request.location.lower()
                for term in ["uk", "england", "britain", "scotland", "wales"]
            )
        ):
            enhanced_query += " UK site:*.co.uk OR site:*.uk"

        logger.info(
            f"🔍 Enhanced {request.search_type.upper()} Search: '{enhanced_query}' ({request.num_results} results)"
        )

        try:
            # Build base parameters
            params = {
                "key": self.api_key,
                "cx": self.search_engine_id,
                "q": enhanced_query,
                "num": min(request.num_results, 10),
                "safe": request.safe_search,
                "lr": f"lang_{request.language}",
                "fields": "items(title,link,snippet,displayLink,image,pagemap),searchInformation(totalResults)",
            }

            # Geographic targeting
            if request.country_code:
                params["gl"] = request.country_code
            elif request.location:
                params["gl"] = self._location_to_country_code(request.location)

            # Search type specific parameters
            if request.search_type == "shopping":
                # For shopping, we'll use regular web search but add shopping-specific query terms
                enhanced_query += " shop buy price store purchase"
                params["q"] = enhanced_query

                # Shopping filters via query modification
                if request.shopping_filters:
                    if request.shopping_filters.min_price is not None:
                        enhanced_query += (
                            f" after:£{request.shopping_filters.min_price}"
                        )
                    if request.shopping_filters.max_price is not None:
                        enhanced_query += (
                            f" before:£{request.shopping_filters.max_price}"
                        )
                    if request.shopping_filters.merchant:
                        enhanced_query += f" site:{request.shopping_filters.merchant}"
                    params["q"] = enhanced_query

            elif request.search_type == "images":
                params["searchType"] = "image"

            elif request.search_type == "news":
                params["tbm"] = "nws"  # News search

            # Date filtering
            if request.date_range:
                params["dateRestrict"] = request.date_range.to_api_format()

            # File type
            if request.file_type:
                params["fileType"] = request.file_type

            # Make the API request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

                data = response.json()
                search_info = data.get("searchInformation", {})
                total_results = int(search_info.get("totalResults", 0))

                # Extract and structure results
                items = data.get("items", [])
                results = []

                for item in items:
                    result = self._extract_enhanced_result(item, request.search_type)
                    if result:
                        results.append(result)

                search_time = (datetime.now() - start_time).total_seconds()

                logger.info(
                    f"✅ Found {len(results)} {request.search_type} results (total: {total_results:,})"
                )

                return SearchResults(
                    results=results,
                    total_found=total_results,
                    search_request=request,
                    query_used=enhanced_query,
                    search_time=search_time,
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("🚫 Google Search quota exceeded (10,000/month limit)")
            else:
                logger.error(f"❌ Google Search API error: {e.response.status_code}")
                if e.response.content:
                    logger.error(f"Error details: {e.response.text[:300]}")

            return SearchResults(
                results=[],
                total_found=0,
                search_request=request,
                query_used=enhanced_query,
                search_time=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.error(f"❌ Unexpected error during enhanced search: {e}")
            return SearchResults(
                results=[],
                total_found=0,
                search_request=request,
                query_used=enhanced_query,
                search_time=(datetime.now() - start_time).total_seconds(),
            )

    def _location_to_country_code(self, location: str) -> str:
        """Convert location string to country code"""
        location_lower = location.lower()

        if any(
            term in location_lower
            for term in ["uk", "england", "britain", "scotland", "wales"]
        ):
            return "uk"
        elif any(
            term in location_lower for term in ["usa", "america", "united states"]
        ):
            return "us"
        elif "canada" in location_lower:
            return "ca"
        elif "australia" in location_lower:
            return "au"
        elif "germany" in location_lower:
            return "de"
        elif "france" in location_lower:
            return "fr"
        else:
            return "uk"  # Default fallback

    def _extract_enhanced_result(
        self, item: Dict[str, Any], search_type: str
    ) -> Optional[SearchResult]:
        """Extract and structure search result data into SearchResult model"""
        try:
            result = SearchResult(
                title=item.get("title", "No Title"),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                display_url=item.get("displayLink", ""),
                search_type=search_type,
            )

            # Extract enriched data from pagemap
            if "pagemap" in item:
                pagemap = item["pagemap"]

                # Image information
                if "cse_thumbnail" in pagemap:
                    thumbnail = pagemap["cse_thumbnail"][0]
                    result.image = {
                        "src": thumbnail.get("src"),
                        "width": thumbnail.get("width"),
                        "height": thumbnail.get("height"),
                    }
                elif "metatags" in pagemap and pagemap["metatags"]:
                    metatags = pagemap["metatags"][0]
                    og_image = metatags.get("og:image")
                    if og_image:
                        result.image = {"src": og_image}

                # Organization/business information
                if "organization" in pagemap:
                    org = pagemap["organization"][0]
                    result.organization = {
                        "name": org.get("name"),
                        "address": org.get("address"),
                        "telephone": org.get("telephone"),
                        "url": org.get("url"),
                    }

                # Rating information
                if "aggregaterating" in pagemap:
                    rating = pagemap["aggregaterating"][0]
                    result.rating = {
                        "value": rating.get("ratingvalue"),
                        "count": rating.get("reviewcount"),
                        "best": rating.get("bestrating"),
                        "worst": rating.get("worstrating"),
                    }

                # Product/price information for shopping results
                if search_type == "shopping":
                    if "product" in pagemap:
                        product = pagemap["product"][0]
                        result.price = {
                            "value": product.get("price"),
                            "currency": product.get("pricecurrency", "GBP"),
                            "availability": product.get("availability"),
                            "condition": product.get("condition"),
                        }

                    # Try to extract price from offers
                    if "offer" in pagemap:
                        offer = pagemap["offer"][0]
                        result.price = {
                            "value": offer.get("price"),
                            "currency": offer.get("pricecurrency", "GBP"),
                            "availability": offer.get("availability"),
                        }

            return result

        except Exception as e:
            logger.warning(f"⚠️  Failed to extract enhanced search result: {e}")
            return None

    async def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Simplified search method for backwards compatibility.

        Converts to SearchRequest and returns legacy format.
        """
        request = SearchRequest(query=query, **kwargs)
        results = await self.enhanced_search(request)

        # Convert to legacy format
        return [
            {
                "title": result.title,
                "link": result.url,
                "snippet": result.snippet,
                "display_link": result.display_url,
                "image": result.image,
                "organization": result.organization,
                "rating": result.rating,
                "price": result.price,
            }
            for result in results.results
        ]


# Export enhanced models and client
__all__ = [
    "SearchRequest",
    "SearchResults",
    "SearchResult",
    "ShoppingFilters",
    "DateRange",
    "GoogleCustomSearchClient",
]
