"""Article dependency - handles article extraction using newspaper3k and goose"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger

from .fetch import FetchResult


@dataclass
class ArticleResult:
    """Result from article extraction using newspaper3k and goose"""
    
    # Basic article info
    title: Optional[str] = None
    text: Optional[str] = None  # Full article text
    summary: Optional[str] = None
    authors: List[str] = None
    
    # Publication metadata
    publish_date: Optional[str] = None
    source_url: Optional[str] = None
    canonical_url: Optional[str] = None
    domain: Optional[str] = None
    
    # Content metadata
    top_image: Optional[str] = None
    images: List[str] = None
    videos: List[str] = None
    tags: List[str] = None
    keywords: List[str] = None
    
    # Article structure
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    meta_lang: Optional[str] = None
    
    # Content analysis
    word_count: Optional[int] = None
    read_time_minutes: Optional[float] = None
    language: Optional[str] = None
    
    # Extraction metadata
    extraction_method: Optional[str] = None  # "newspaper3k", "goose", "fallback"
    extraction_successful: bool = False
    confidence_score: Optional[float] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.images is None:
            self.images = []
        if self.videos is None:
            self.videos = []
        if self.tags is None:
            self.tags = []
        if self.keywords is None:
            self.keywords = []
        
        # Calculate word count and read time if we have text
        if self.text:
            words = len(self.text.split())
            self.word_count = words
            # Average reading speed: 200-250 WPM, use 225
            self.read_time_minutes = round(words / 225.0, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class ArticleDependency:
    """
    Dependency for extracting article content using newspaper3k and goose.
    
    Provides robust article extraction with fallback strategies:
    1. Try newspaper3k first (generally more reliable)
    2. Fallback to goose if newspaper3k fails
    3. Basic HTML parsing as last resort
    """
    
    def __init__(self, prefer_newspaper: bool = True, language: str = "en"):
        self.prefer_newspaper = prefer_newspaper
        self.language = language
        self.required_packages = ["newspaper3k", "goose3"]
    
    def _check_dependencies(self) -> Dict[str, bool]:
        """Check which article extraction libraries are available"""
        availability = {}
        
        try:
            import newspaper
            availability['newspaper3k'] = True
        except ImportError:
            availability['newspaper3k'] = False
            
        try:
            from goose3 import Goose
            availability['goose3'] = True
        except ImportError:
            availability['goose3'] = False
            
        return availability
    
    def _extract_with_newspaper(self, fetch_result: FetchResult) -> ArticleResult:
        """Extract article using newspaper3k"""
        try:
            import newspaper
            from newspaper import Article
            
            logger.info(f"ArticleDependency: Extracting with newspaper3k from {fetch_result.url}")
            
            # Create article from URL
            article = Article(fetch_result.url, language=self.language)
            
            # Set the HTML directly to avoid re-fetching
            article.set_html(fetch_result.content)
            article.parse()
            
            # Try to get additional metadata
            try:
                article.nlp()  # This might fail, so wrap in try-catch
            except Exception as e:
                logger.warning(f"NLP processing failed for article: {e}")
            
            # Parse domain from URL
            domain = urlparse(fetch_result.url).netloc
            
            # Calculate confidence based on what we extracted
            confidence = 0.0
            if article.title:
                confidence += 0.3
            if article.text and len(article.text.strip()) > 100:
                confidence += 0.4
            if article.authors:
                confidence += 0.1
            if article.publish_date:
                confidence += 0.1
            if article.summary:
                confidence += 0.1
            
            result = ArticleResult(
                title=article.title,
                text=article.text,
                summary=article.summary if hasattr(article, 'summary') else None,
                authors=article.authors or [],
                
                publish_date=article.publish_date.isoformat() if article.publish_date else None,
                source_url=fetch_result.url,
                canonical_url=article.canonical_link or fetch_result.url,
                domain=domain,
                
                top_image=article.top_image,
                images=list(article.images) if article.images else [],
                videos=list(article.movies) if hasattr(article, 'movies') and article.movies else [],
                tags=list(article.tags) if hasattr(article, 'tags') and article.tags else [],
                keywords=list(article.keywords) if hasattr(article, 'keywords') and article.keywords else [],
                
                meta_description=article.meta_description,
                meta_keywords=article.meta_keywords,
                meta_lang=article.meta_lang,
                language=self.language,
                
                extraction_method="newspaper3k",
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            logger.info(f"ArticleDependency: Newspaper3k extracted '{result.title}' ({result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"ArticleDependency: Newspaper3k extraction failed: {e}")
            return ArticleResult(
                source_url=fetch_result.url,
                extraction_method="newspaper3k",
                extraction_successful=False,
                error=f"Newspaper3k failed: {str(e)}"
            )
    
    def _extract_with_goose(self, fetch_result: FetchResult) -> ArticleResult:
        """Extract article using goose3"""
        try:
            from goose3 import Goose
            
            logger.info(f"ArticleDependency: Extracting with goose3 from {fetch_result.url}")
            
            # Configure goose
            config = {
                'browser_user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'http_timeout': 30,
            }
            
            with Goose(config) as g:
                # Extract from raw HTML
                article = g.extract(raw_html=fetch_result.content)
                
                # Parse domain
                domain = urlparse(fetch_result.url).netloc
                
                # Calculate confidence
                confidence = 0.0
                if article.title:
                    confidence += 0.3
                if article.cleaned_text and len(article.cleaned_text.strip()) > 100:
                    confidence += 0.4
                if article.authors:
                    confidence += 0.1
                if article.publish_date:
                    confidence += 0.1
                if article.meta_description:
                    confidence += 0.1
                
                result = ArticleResult(
                    title=article.title,
                    text=article.cleaned_text,
                    authors=article.authors if article.authors else [],
                    
                    publish_date=article.publish_date if article.publish_date else None,
                    source_url=fetch_result.url,
                    canonical_url=article.canonical_link or fetch_result.url,
                    domain=domain,
                    
                    top_image=article.top_image.src if article.top_image else None,
                    images=[img.src for img in article.images] if article.images else [],
                    
                    meta_description=article.meta_description,
                    meta_keywords=article.meta_keywords,
                    meta_lang=article.meta_lang,
                    language=self.language,
                    
                    extraction_method="goose3",
                    extraction_successful=True,
                    confidence_score=confidence,
                )
                
                logger.info(f"ArticleDependency: Goose3 extracted '{result.title}' ({result.word_count} words)")
                return result
                
        except Exception as e:
            logger.error(f"ArticleDependency: Goose3 extraction failed: {e}")
            return ArticleResult(
                source_url=fetch_result.url,
                extraction_method="goose3",
                extraction_successful=False,
                error=f"Goose3 failed: {str(e)}"
            )
    
    def _fallback_extraction(self, fetch_result: FetchResult) -> ArticleResult:
        """Basic fallback extraction using BeautifulSoup"""
        try:
            from bs4 import BeautifulSoup
            
            logger.info(f"ArticleDependency: Fallback extraction from {fetch_result.url}")
            
            soup = BeautifulSoup(fetch_result.content, 'html.parser')
            
            # Try to extract basic information
            title = None
            
            # Try various title selectors
            title_selectors = [
                'h1',
                'title',
                '[property="og:title"]',
                '[name="twitter:title"]',
                '.title',
                '.headline'
            ]
            
            for selector in title_selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text().strip()
                    if title:
                        break
            
            # Try to extract main content
            text = ""
            content_selectors = [
                'article',
                '.content',
                '.article-content',
                '.post-content',
                'main',
                '.entry-content'
            ]
            
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if len(text) > 100:  # Only use if substantial content
                        break
            
            # If no content found, try paragraphs
            if not text:
                paragraphs = soup.find_all('p')
                text = ' '.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            # Extract meta description
            meta_desc = None
            meta_element = soup.find('meta', attrs={'name': 'description'})
            if meta_element:
                meta_desc = meta_element.get('content')
            
            domain = urlparse(fetch_result.url).netloc
            
            confidence = 0.2  # Low confidence for fallback
            if title:
                confidence += 0.3
            if text and len(text) > 100:
                confidence += 0.3
            
            result = ArticleResult(
                title=title,
                text=text,
                source_url=fetch_result.url,
                canonical_url=fetch_result.url,
                domain=domain,
                meta_description=meta_desc,
                extraction_method="fallback",
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            logger.info(f"ArticleDependency: Fallback extracted '{result.title}' ({result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"ArticleDependency: Fallback extraction failed: {e}")
            return ArticleResult(
                source_url=fetch_result.url,
                extraction_method="fallback",
                extraction_successful=False,
                error=f"Fallback extraction failed: {str(e)}"
            )
    
    async def extract_article(self, fetch_result: FetchResult) -> ArticleResult:
        """
        Extract article content with fallback strategies.
        
        Args:
            fetch_result: Result from FetchDependency containing HTML content
            
        Returns:
            ArticleResult with extracted content and metadata
        """
        if not fetch_result or not fetch_result.content:
            return ArticleResult(
                source_url=fetch_result.url if fetch_result else "unknown",
                extraction_successful=False,
                error="No content to extract from"
            )
        
        availability = self._check_dependencies()
        
        # Strategy 1: Try newspaper3k if available and preferred
        if self.prefer_newspaper and availability.get('newspaper3k'):
            result = self._extract_with_newspaper(fetch_result)
            if result.extraction_successful and result.confidence_score and result.confidence_score > 0.5:
                return result
        
        # Strategy 2: Try goose3 if available
        if availability.get('goose3'):
            result = self._extract_with_goose(fetch_result)
            if result.extraction_successful and result.confidence_score and result.confidence_score > 0.5:
                return result
        
        # Strategy 3: Try newspaper3k if we haven't yet
        if not self.prefer_newspaper and availability.get('newspaper3k'):
            result = self._extract_with_newspaper(fetch_result)
            if result.extraction_successful and result.confidence_score and result.confidence_score > 0.5:
                return result
        
        # Strategy 4: Fallback to basic extraction
        logger.warning("ArticleDependency: Using fallback extraction method")
        result = self._fallback_extraction(fetch_result)
        
        if not result.extraction_successful:
            logger.error("ArticleDependency: All extraction methods failed")
            
        return result


# Export
__all__ = ["ArticleDependency", "ArticleResult"]