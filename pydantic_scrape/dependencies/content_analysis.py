"""Content analysis dependency - handles content type detection and extraction"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .fetch import FetchResult


@dataclass
class ContentAnalysisResult:
    """Result from content analysis"""

    content_type: str  # "science", "news", "social", "generic"
    confidence: float  # 0.0 to 1.0

    # Science-specific extractions
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None

    # General extractions
    extracted_data: Dict[str, Any] = None

    # Analysis metadata
    indicators_found: List[str] = None
    analysis_method: str = None

    def __post_init__(self):
        if self.extracted_data is None:
            self.extracted_data = {}
        if self.indicators_found is None:
            self.indicators_found = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class ContentAnalysisDependency:
    """
    Dependency for analyzing content type and extracting metadata.

    Handles all the heavy lifting for content detection and extraction.
    """

    def __init__(self):
        # Science domain indicators
        self.science_domains = [
            "arxiv.org",
            "doi.org",
            "pubmed",
            "nature.com",
            "science.org",
            "sciencedirect.com",
            "springer.com",
            "wiley.com",
            "cell.com",
            "plos.org",
            "bioRxiv.org",
            "medRxiv.org",
            "researchgate.net",
        ]

        # News domain indicators
        self.news_domains = [
            "news",
            "reuters",
            "bbc",
            "cnn",
            "nytimes",
            "washingtonpost",
            "guardian",
            "forbes",
            "techcrunch",
            "wired",
        ]

        # Social media indicators
        self.social_domains = [
            "twitter.com",
            "x.com",
            "facebook.com",
            "linkedin.com",
            "reddit.com",
            "youtube.com",
            "instagram.com",
        ]

    async def analyze_content(self, fetch_result: FetchResult) -> ContentAnalysisResult:
        """
        Analyze content and determine type with confidence.

        Args:
            fetch_result: Result from fetch dependency

        Returns:
            ContentAnalysisResult with type, confidence, and extracted data
        """
        url = fetch_result.url.lower()
        content = fetch_result.content or ""

        # Try science detection first
        science_result = self._analyze_science_content(url, content, fetch_result)
        if science_result.confidence > 0.7:
            return science_result

        # Try news detection
        news_result = self._analyze_news_content(url, content, fetch_result)
        if news_result.confidence > 0.7:
            return news_result

        # Try social media detection
        social_result = self._analyze_social_content(url, content, fetch_result)
        if social_result.confidence > 0.7:
            return social_result

        # Default to generic with low confidence
        return ContentAnalysisResult(
            content_type="generic", confidence=0.3, analysis_method="fallback"
        )

    def _analyze_science_content(
        self, url: str, content: str, fetch_result: FetchResult
    ) -> ContentAnalysisResult:
        """Analyze if content is science-related"""
        indicators_found = []
        confidence = 0.0
        extracted_data = {}

        # Check domain indicators
        domain_matches = [domain for domain in self.science_domains if domain in url]
        if domain_matches:
            indicators_found.extend(domain_matches)
            confidence += 0.6

        # Check for DOI
        doi = self._extract_doi(content)
        if doi:
            indicators_found.append("doi_found")
            extracted_data["doi"] = doi
            confidence += 0.4

        # Check for ArXiv ID
        arxiv_id = self._extract_arxiv_id(url, content)
        if arxiv_id:
            indicators_found.append("arxiv_id_found")
            extracted_data["arxiv_id"] = arxiv_id
            confidence += 0.3

        # Check for PubMed ID
        pubmed_id = self._extract_pubmed_id(url, content)
        if pubmed_id:
            indicators_found.append("pubmed_id_found")
            extracted_data["pubmed_id"] = pubmed_id
            confidence += 0.3

        # Check for science keywords in content
        science_keywords = [
            "abstract",
            "citation",
            "doi",
            "journal",
            "research",
            "study",
            "paper",
        ]
        keyword_matches = [kw for kw in science_keywords if kw in content.lower()]
        if len(keyword_matches) >= 3:
            indicators_found.append(f"science_keywords_{len(keyword_matches)}")
            confidence += 0.2

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return ContentAnalysisResult(
            content_type="science",
            confidence=confidence,
            doi=doi,
            arxiv_id=arxiv_id,
            pubmed_id=pubmed_id,
            extracted_data=extracted_data,
            indicators_found=indicators_found,
            analysis_method="domain_and_content",
        )

    def _analyze_news_content(
        self, url: str, content: str, fetch_result: FetchResult
    ) -> ContentAnalysisResult:
        """Analyze if content is news-related"""
        indicators_found = []
        confidence = 0.0

        # Check domain indicators
        domain_matches = [domain for domain in self.news_domains if domain in url]
        if domain_matches:
            indicators_found.extend(domain_matches)
            confidence += 0.8

        # Check for news keywords
        news_keywords = ["breaking", "reporter", "published", "updated", "source"]
        keyword_matches = [kw for kw in news_keywords if kw in content.lower()]
        if len(keyword_matches) >= 2:
            indicators_found.append(f"news_keywords_{len(keyword_matches)}")
            confidence += 0.3

        confidence = min(confidence, 1.0)

        return ContentAnalysisResult(
            content_type="news",
            confidence=confidence,
            indicators_found=indicators_found,
            analysis_method="domain_and_keywords",
        )

    def _analyze_social_content(
        self, url: str, content: str, fetch_result: FetchResult
    ) -> ContentAnalysisResult:
        """Analyze if content is social media-related"""
        indicators_found = []
        confidence = 0.0

        # Check domain indicators
        domain_matches = [domain for domain in self.social_domains if domain in url]
        if domain_matches:
            indicators_found.extend(domain_matches)
            confidence = 0.9

        return ContentAnalysisResult(
            content_type="social",
            confidence=confidence,
            indicators_found=indicators_found,
            analysis_method="domain_detection",
        )

    def _extract_doi(self, content: str) -> Optional[str]:
        """Extract DOI from content"""
        import re

        doi_pattern = r"10\.\d{4,9}/[-._;()/:A-Z0-9]+"
        match = re.search(doi_pattern, content, re.IGNORECASE)
        return match.group(0) if match else None

    def _extract_arxiv_id(self, url: str, content: str) -> Optional[str]:
        """Extract ArXiv ID from URL or content"""
        import re

        # Try URL first
        arxiv_url_pattern = r"arxiv\.org/abs/(\d+\.\d+)"
        match = re.search(arxiv_url_pattern, url)
        if match:
            return match.group(1)

        # Try content
        arxiv_content_pattern = r"arXiv:(\d+\.\d+)"
        match = re.search(arxiv_content_pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_pubmed_id(self, url: str, content: str) -> Optional[str]:
        """Extract PubMed ID from URL or content"""
        import re

        # Try URL first
        pubmed_url_pattern = r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)"
        match = re.search(pubmed_url_pattern, url)
        if match:
            return match.group(1)

        # Try content
        pmid_pattern = r"PMID:\s*(\d+)"
        match = re.search(pmid_pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def detect_content_type(self, fetch_result: FetchResult) -> str:
        """Simple content type detection (convenience method)"""
        import asyncio

        result = asyncio.run(self.analyze_content(fetch_result))
        return result.content_type

    def extract_science_metadata(self, fetch_result: FetchResult) -> Dict[str, Any]:
        """Extract science-specific metadata (convenience method)"""
        import asyncio

        result = asyncio.run(self.analyze_content(fetch_result))

        if result.content_type == "science":
            return {
                "doi": result.doi,
                "arxiv_id": result.arxiv_id,
                "pubmed_id": result.pubmed_id,
                "confidence": result.confidence,
                "indicators": result.indicators_found,
            }
        return {}


__all__ = ["ContentAnalysisDependency", "ContentAnalysisResult"]
