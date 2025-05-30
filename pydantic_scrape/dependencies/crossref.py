"""Crossref dependency - handles metadata lookup via Crossref API"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from habanero import Crossref
from loguru import logger


@dataclass
class CrossrefResult:
    """Result from Crossref metadata lookup"""

    crossref_doi: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = None
    journal_name: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    citation_count: Optional[int] = None
    article_type: Optional[str] = None
    issn: List[str] = None
    isbn: List[str] = None
    references: List[Dict[str, Any]] = None
    funders: List[Dict[str, Any]] = None
    license_info: Optional[Dict[str, Any]] = None

    # Lookup metadata
    lookup_successful: bool = False
    error: Optional[str] = None

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.issn is None:
            self.issn = []
        if self.isbn is None:
            self.isbn = []
        if self.references is None:
            self.references = []
        if self.funders is None:
            self.funders = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class CrossrefDependency:
    """
    Dependency for looking up academic paper metadata via Crossref API.

    Provides reusable Crossref lookup functionality for any node.
    """

    def __init__(self):
        self.required_packages = ["habanero"]
    
    def _check_dependencies(self) -> bool:
        """Check if required packages are available"""
        try:
            import habanero
            return True
        except ImportError as e:
            logger.warning(f"Crossref dependency missing packages: {e}")
            return False

    async def lookup_by_doi(self, doi: str) -> CrossrefResult:
        """Look up paper by DOI"""
        if not self._check_dependencies():
            return CrossrefResult(error="Missing required package: habanero")

        try:
            cr = Crossref()
            result = cr.works(ids=doi)

            if result and "message" in result:
                work = result["message"]
                return self._parse_crossref_work(work)
            else:
                return CrossrefResult(error=f"No work found for DOI: {doi}")

        except Exception as e:
            logger.error(f"Crossref DOI lookup failed: {e}")
            return CrossrefResult(error=str(e))

    async def lookup_by_title(self, title: str) -> CrossrefResult:
        """Look up paper by title"""
        if not self._check_dependencies():
            return CrossrefResult(error="Missing required package: habanero")

        try:
            cr = Crossref()
            clean_title = title.strip()
            result = cr.works(query_title=clean_title, limit=5)

            if result and "message" in result and "items" in result["message"]:
                items = result["message"]["items"]
                if items:
                    # Take the first result - Crossref ranks by relevance
                    work = items[0]
                    return self._parse_crossref_work(work)
                else:
                    return CrossrefResult(error=f"No works found for title: {title}")
            else:
                return CrossrefResult(
                    error=f"No results from Crossref for title: {title}"
                )

        except Exception as e:
            logger.error(f"Crossref title lookup failed: {e}")
            return CrossrefResult(error=str(e))

    async def lookup(
        self, doi: Optional[str] = None, title: Optional[str] = None
    ) -> CrossrefResult:
        """
        Smart lookup that tries DOI first, falls back to title.

        Args:
            doi: DOI to look up
            title: Title to look up if DOI fails

        Returns:
            CrossrefResult with metadata or error
        """
        # Try DOI first if available
        if doi:
            result = await self.lookup_by_doi(doi)
            if result.lookup_successful:
                return result

        # Fall back to title search
        if title:
            return await self.lookup_by_title(title)

        return CrossrefResult(error="No DOI or title provided for lookup")

    def _parse_crossref_work(self, work: Dict[str, Any]) -> CrossrefResult:
        """Parse Crossref work data into result object"""
        try:
            # Extract basic info
            result = CrossrefResult(
                crossref_doi=work.get("DOI", ""),
                title=work.get("title", [""])[0] if work.get("title") else "",
                article_type=work.get("type", ""),
                lookup_successful=True,
            )

            # Authors
            authors = work.get("author", [])
            result.authors = [
                f"{auth.get('given', '')} {auth.get('family', '')}".strip()
                for auth in authors
                if auth.get("given") or auth.get("family")
            ]

            # Journal/Container info
            container = work.get("container-title", [])
            result.journal_name = container[0] if container else ""
            result.publisher = work.get("publisher", "")

            # Publication date
            pub_date = work.get("published-print") or work.get("published-online")
            if pub_date and "date-parts" in pub_date:
                date_parts = pub_date["date-parts"][0]
                if len(date_parts) >= 3:
                    result.publication_date = (
                        f"{date_parts[0]}-{date_parts[1]:02d}-{date_parts[2]:02d}"
                    )
                elif len(date_parts) >= 2:
                    result.publication_date = f"{date_parts[0]}-{date_parts[1]:02d}"
                elif len(date_parts) >= 1:
                    result.publication_date = str(date_parts[0])

            # Citation count (if available)
            result.citation_count = work.get("is-referenced-by-count", 0)

            # ISSN/ISBN
            result.issn = work.get("ISSN", [])
            result.isbn = work.get("ISBN", [])

            # References
            result.references = work.get("reference", [])

            # Funders
            result.funders = work.get("funder", [])

            # License
            licenses = work.get("license", [])
            result.license_info = licenses[0] if licenses else None

            logger.info(f"Crossref lookup successful: {result.crossref_doi}")
            return result

        except Exception as e:
            logger.error(f"Error parsing Crossref work: {e}")
            return CrossrefResult(error=f"Error parsing Crossref data: {str(e)}")
