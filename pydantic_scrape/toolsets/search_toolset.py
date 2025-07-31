"""
Search Toolset

Independent search functionality that can be used by any agent.
Provides enhanced Google search capabilities with rich filtering.
"""

from loguru import logger
from pydantic_ai import RunContext

from pydantic_scrape.dependencies.google_search import (
    GoogleCustomSearchClient,
    SearchRequest,
)


async def enhanced_search(ctx: RunContext, request: SearchRequest) -> str:
    """
    Perform enhanced search with rich filtering and structured results.

    This unified search interface supports:
    - Web search (general results)
    - Shopping search (products, prices, reviews)
    - Image and news search
    - Advanced filtering (location, sites, dates, prices)

    Args:
        ctx: Run context (standard pydantic-ai pattern)
        request: SearchRequest with all search parameters and filters

    Returns:
        String with formatted search results and metadata
    """
    try:
        logger.info(f"🔍 Enhanced {request.search_type} search: '{request.query}'")

        # Create Google client on demand
        google_client = GoogleCustomSearchClient()
        results = await google_client.enhanced_search(request)

        if not results.results:
            return f"No {request.search_type} search results found for: {request.query}"

        # Format results for AI consumption
        formatted_results = []
        formatted_results.append(
            f"=== ENHANCED {request.search_type.upper()} SEARCH RESULTS ==="
        )
        formatted_results.append(f"Query: {results.query_used}")
        formatted_results.append(
            f"Results: {len(results.results)} of {results.total_found:,} found"
        )
        formatted_results.append(f"Search time: {results.search_time:.2f}s")
        formatted_results.append("")

        for i, result in enumerate(results.results, 1):
            formatted_results.append(f"{i}. {result.title}")
            formatted_results.append(f"   URL: {result.url}")
            formatted_results.append(f"   Snippet: {result.snippet}")

            # Add shopping-specific information
            if result.price and request.search_type == "shopping":
                price_info = result.price
                if price_info.get("value"):
                    formatted_results.append(
                        f"   💰 Price: {price_info['currency']} {price_info['value']}"
                    )
                if price_info.get("availability"):
                    formatted_results.append(
                        f"   📦 Availability: {price_info['availability']}"
                    )

            # Add organization information
            if result.organization:
                org = result.organization
                if org.get("name"):
                    formatted_results.append(f"   🏢 Organization: {org['name']}")
                if org.get("telephone"):
                    formatted_results.append(f"   📞 Phone: {org['telephone']}")

            # Add rating information
            if result.rating:
                rating = result.rating
                if rating.get("value") and rating.get("count"):
                    formatted_results.append(
                        f"   ⭐ Rating: {rating['value']}/5 ({rating['count']} reviews)"
                    )

            formatted_results.append("")

        formatted_results.append("=== END SEARCH RESULTS ===")

        final_result = "\n".join(formatted_results)
        logger.info(f"✅ Enhanced search completed: {len(results.results)} results")
        return final_result

    except Exception as e:
        logger.error(f"❌ Enhanced search failed: {e}")
        return f"Enhanced search failed: {str(e)}"


# Export the search tools
__all__ = ["enhanced_search"]