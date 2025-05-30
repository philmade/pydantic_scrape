"""OpenAlex dependency - handles metadata lookup via OpenAlex API"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from loguru import logger
from pyalex import Works
from rapidfuzz import fuzz


@dataclass
class OpenAlexResult:
    """Result from OpenAlex metadata lookup"""

    openalex_id: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = None
    journal_name: Optional[str] = None
    publication_date: Optional[str] = None
    citation_count: Optional[int] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    concepts: List[Dict[str, Any]] = None
    open_access_type: Optional[str] = None
    pdf_urls: List[str] = None

    # Lookup metadata
    match_method: Optional[str] = None  # "doi", "title_fuzzy", etc.
    title_match_score: Optional[float] = None
    lookup_successful: bool = False
    error: Optional[str] = None

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.concepts is None:
            self.concepts = []
        if self.pdf_urls is None:
            self.pdf_urls = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class OpenAlexDependency:
    """
    Dependency for looking up academic paper metadata via OpenAlex API.

    Provides reusable OpenAlex lookup functionality for any node.
    """

    def __init__(self, fuzzy_match_threshold: float = 85.0):
        self.fuzzy_match_threshold = fuzzy_match_threshold
        self.required_packages = ["pyalex", "rapidfuzz"]
    
    def _check_dependencies(self) -> bool:
        """Check if required packages are available"""
        try:
            import pyalex
            import rapidfuzz
            return True
        except ImportError as e:
            logger.warning(f"OpenAlex dependency missing packages: {e}")
            return False

    async def lookup_by_doi(self, doi: str) -> OpenAlexResult:
        """Look up paper by DOI"""
        if not self._check_dependencies():
            return OpenAlexResult(error="Missing required packages: pyalex, rapidfuzz")

        try:
            from pyalex import Works

            works = Works().filter(doi=doi).get()
            if works:
                work = works[0]
                return self._parse_openalex_work(work, "doi", 100.0)
            else:
                return OpenAlexResult(error=f"No work found for DOI: {doi}")

        except Exception as e:
            logger.error(f"OpenAlex DOI lookup failed: {e}")
            return OpenAlexResult(error=str(e))

    async def lookup_by_title(self, title: str) -> OpenAlexResult:
        """Look up paper by title with fuzzy matching"""
        if not self._check_dependencies():
            return OpenAlexResult(error="Missing required packages: pyalex, rapidfuzz")
            
        try:
            # Search for title
            clean_title = title.strip()
            works = Works().search(clean_title).get()

            if not works:
                return OpenAlexResult(error=f"No works found for title: {title}")

            # Find best fuzzy match
            best_match = None
            best_score = 0

            for candidate in works[:5]:  # Check top 5 results
                candidate_title = candidate.get("title", "")
                if candidate_title:
                    score = fuzz.ratio(clean_title.lower(), candidate_title.lower())
                    if score > best_score and score >= self.fuzzy_match_threshold:
                        best_score = score
                        best_match = candidate

            if best_match:
                return self._parse_openalex_work(best_match, "title_fuzzy", best_score)
            else:
                return OpenAlexResult(
                    error=f"No good title match found (threshold: {self.fuzzy_match_threshold})"
                )

        except Exception as e:
            logger.error(f"OpenAlex title lookup failed: {e}")
            return OpenAlexResult(error=str(e))

    async def lookup(
        self, doi: Optional[str] = None, title: Optional[str] = None
    ) -> OpenAlexResult:
        """
        Smart lookup that tries DOI first, falls back to title.

        Args:
            doi: DOI to look up
            title: Title to look up if DOI fails

        Returns:
            OpenAlexResult with metadata or error
        """
        # Try DOI first if available
        if doi:
            result = await self.lookup_by_doi(doi)
            if result.lookup_successful:
                return result

        # Fall back to title search
        if title:
            return await self.lookup_by_title(title)

        return OpenAlexResult(error="No DOI or title provided for lookup")

    def _parse_openalex_work(
        self, work: Dict[str, Any], match_method: str, match_score: float
    ) -> OpenAlexResult:
        """Parse OpenAlex work data into result object"""
        try:
            # Extract basic info
            result = OpenAlexResult(
                openalex_id=work.get("id", "").replace("https://openalex.org/", ""),
                title=work.get("title", ""),
                doi=work.get("doi", "").replace("https://doi.org/", "")
                if work.get("doi")
                else None,
                match_method=match_method,
                title_match_score=match_score,
                lookup_successful=True,
            )

            # Authors
            authorships = work.get("authorships", [])
            result.authors = [
                auth.get("author", {}).get("display_name", "")
                for auth in authorships
                if auth.get("author", {}).get("display_name")
            ]

            # Journal info
            primary_location = work.get("primary_location", {})
            source = primary_location.get("source", {})
            result.journal_name = source.get("display_name", "")

            # Publication date
            result.publication_date = work.get("publication_date", "")

            # Citations
            result.citation_count = work.get("cited_by_count", 0)

            # Concepts
            result.concepts = work.get("concepts", [])

            # Open access
            open_access = work.get("open_access", {})
            result.open_access_type = open_access.get("oa_type", "")

            # PDF URLs
            locations = work.get("locations", [])
            result.pdf_urls = [
                loc.get("pdf_url", "") for loc in locations if loc.get("pdf_url")
            ]

            logger.info(f"OpenAlex lookup successful: {result.openalex_id}")
            return result

        except Exception as e:
            logger.error(f"Error parsing OpenAlex work: {e}")
            return OpenAlexResult(error=f"Error parsing OpenAlex data: {str(e)}")
