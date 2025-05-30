"""Document dependency - handles document download and text extraction"""

import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import mimetypes

from loguru import logger

from .fetch import FetchResult


@dataclass
class DocumentResult:
    """Result from document download and text extraction"""
    
    # Basic document info
    title: Optional[str] = None
    text: Optional[str] = None  # Full extracted text
    summary: Optional[str] = None
    author: Optional[str] = None
    creator: Optional[str] = None
    
    # Document metadata
    file_type: Optional[str] = None  # "pdf", "docx", "epub", etc.
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    
    # Document properties
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    subject: Optional[str] = None
    keywords: List[str] = None
    language: Optional[str] = None
    
    # Content analysis
    word_count: Optional[int] = None
    character_count: Optional[int] = None
    read_time_minutes: Optional[float] = None
    
    # File storage
    binary_content: Optional[bytes] = None
    temp_file_path: Optional[str] = None  # Temporary file path if saved
    
    # Extraction metadata
    extraction_method: Optional[str] = None  # "pymupdf", "docx", "ebooklib", etc.
    extraction_successful: bool = False
    confidence_score: Optional[float] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        
        # Calculate content metrics if we have text
        if self.text:
            self.character_count = len(self.text)
            words = len(self.text.split())
            self.word_count = words
            # Average reading speed: 200-250 WPM, use 225
            self.read_time_minutes = round(words / 225.0, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization (excluding binary content)"""
        result = asdict(self)
        # Exclude binary content from serialization (too large)
        result.pop('binary_content', None)
        # Include file size info instead
        if self.binary_content:
            result['has_binary_content'] = True
            result['binary_size_bytes'] = len(self.binary_content)
        else:
            result['has_binary_content'] = False
        return result


class DocumentDependency:
    """
    Dependency for downloading and extracting text from documents.
    
    Supports:
    - PDF files (using PyMuPDF)
    - Word documents (using python-docx)  
    - EPUB files (using ebooklib)
    - Text files (direct reading)
    - Fallback text extraction
    """
    
    def __init__(self, save_binary: bool = True, save_temp_file: bool = False):
        self.save_binary = save_binary
        self.save_temp_file = save_temp_file
        self.required_packages = ["PyMuPDF", "python-docx", "ebooklib"]
    
    def _check_dependencies(self) -> Dict[str, bool]:
        """Check which document processing libraries are available"""
        availability = {}
        
        try:
            import fitz  # PyMuPDF
            availability['pymupdf'] = True
        except ImportError:
            availability['pymupdf'] = False
            
        try:
            import docx
            availability['python-docx'] = True
        except ImportError:
            availability['python-docx'] = False
            
        try:
            import ebooklib
            availability['ebooklib'] = True
        except ImportError:
            availability['ebooklib'] = False
            
        return availability
    
    def _detect_file_type(self, url: str, content: bytes) -> tuple[str, str]:
        """Detect file type from URL and content"""
        # Try URL extension first
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        
        if path.endswith('.pdf'):
            return 'pdf', 'application/pdf'
        elif path.endswith(('.doc', '.docx')):
            return 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif path.endswith('.epub'):
            return 'epub', 'application/epub+zip'
        elif path.endswith('.txt'):
            return 'txt', 'text/plain'
        
        # Try MIME type detection from content
        if content:
            # PDF magic number
            if content.startswith(b'%PDF'):
                return 'pdf', 'application/pdf'
            # ZIP-based formats (DOCX, EPUB)
            elif content.startswith(b'PK'):
                # Could be DOCX or EPUB, need deeper inspection
                if b'word/' in content[:1000]:
                    return 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                elif b'epub' in content[:1000] or b'application/epub' in content[:1000]:
                    return 'epub', 'application/epub+zip'
            
        # Fallback
        return 'unknown', 'application/octet-stream'
    
    def _extract_pdf_text(self, content: bytes) -> DocumentResult:
        """Extract text from PDF using PyMuPDF"""
        try:
            import fitz
            
            logger.info("DocumentDependency: Extracting PDF with PyMuPDF")
            
            # Open PDF from bytes
            doc = fitz.open(stream=content, filetype="pdf")
            
            # Extract text from all pages
            text_parts = []
            for page_num in range(doc.page_count):
                page = doc[page_num]
                text_parts.append(page.get_text())
            
            text = '\n'.join(text_parts)
            
            # Extract metadata
            metadata = doc.metadata
            
            # Calculate confidence based on text extracted
            confidence = 0.5  # Base confidence for PDF
            if text and len(text.strip()) > 100:
                confidence += 0.3
            if metadata.get('title'):
                confidence += 0.1
            if metadata.get('author'):
                confidence += 0.1
            
            result = DocumentResult(
                title=metadata.get('title') or None,
                text=text.strip() if text else None,
                author=metadata.get('author') or None,
                creator=metadata.get('creator') or None,
                subject=metadata.get('subject') or None,
                keywords=metadata.get('keywords', '').split(',') if metadata.get('keywords') else [],
                
                file_type='pdf',
                mime_type='application/pdf',
                file_size_bytes=len(content),
                page_count=doc.page_count,
                
                creation_date=metadata.get('creationDate'),
                modification_date=metadata.get('modDate'),
                
                binary_content=content if self.save_binary else None,
                
                extraction_method='pymupdf',
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            doc.close()
            logger.info(f"DocumentDependency: PyMuPDF extracted '{result.title}' ({result.page_count} pages, {result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"DocumentDependency: PyMuPDF extraction failed: {e}")
            return DocumentResult(
                file_type='pdf',
                binary_content=content if self.save_binary else None,
                extraction_method='pymupdf',
                extraction_successful=False,
                error=f"PyMuPDF failed: {str(e)}"
            )
    
    def _extract_docx_text(self, content: bytes) -> DocumentResult:
        """Extract text from Word document using python-docx"""
        try:
            import docx
            from io import BytesIO
            
            logger.info("DocumentDependency: Extracting DOCX with python-docx")
            
            # Open document from bytes
            doc = docx.Document(BytesIO(content))
            
            # Extract text from all paragraphs
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            text = '\n'.join(text_parts)
            
            # Extract basic metadata
            props = doc.core_properties
            
            confidence = 0.5  # Base confidence for DOCX
            if text and len(text.strip()) > 100:
                confidence += 0.3
            if props.title:
                confidence += 0.1
            if props.author:
                confidence += 0.1
            
            result = DocumentResult(
                title=props.title or None,
                text=text.strip() if text else None,
                author=props.author or None,
                creator=props.creator or None,
                subject=props.subject or None,
                keywords=props.keywords.split(',') if props.keywords else [],
                
                file_type='docx',
                mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                file_size_bytes=len(content),
                
                creation_date=props.created.isoformat() if props.created else None,
                modification_date=props.modified.isoformat() if props.modified else None,
                
                binary_content=content if self.save_binary else None,
                
                extraction_method='python-docx',
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            logger.info(f"DocumentDependency: python-docx extracted '{result.title}' ({result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"DocumentDependency: python-docx extraction failed: {e}")
            return DocumentResult(
                file_type='docx',
                binary_content=content if self.save_binary else None,
                extraction_method='python-docx',
                extraction_successful=False,
                error=f"python-docx failed: {str(e)}"
            )
    
    def _extract_epub_text(self, content: bytes) -> DocumentResult:
        """Extract text from EPUB using ebooklib"""
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
            from io import BytesIO
            
            logger.info("DocumentDependency: Extracting EPUB with ebooklib")
            
            # Open EPUB from bytes
            book = epub.read_epub(BytesIO(content))
            
            # Extract text from all items
            text_parts = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text_parts.append(soup.get_text())
            
            text = '\n'.join(text_parts)
            
            # Extract metadata
            title = book.get_metadata('DC', 'title')
            title = title[0][0] if title else None
            
            authors = book.get_metadata('DC', 'creator')
            author = authors[0][0] if authors else None
            
            subject = book.get_metadata('DC', 'subject')
            subject = subject[0][0] if subject else None
            
            language = book.get_metadata('DC', 'language')
            language = language[0][0] if language else None
            
            confidence = 0.5  # Base confidence for EPUB
            if text and len(text.strip()) > 100:
                confidence += 0.3
            if title:
                confidence += 0.1
            if author:
                confidence += 0.1
            
            result = DocumentResult(
                title=title,
                text=text.strip() if text else None,
                author=author,
                subject=subject,
                language=language,
                
                file_type='epub',
                mime_type='application/epub+zip',
                file_size_bytes=len(content),
                
                binary_content=content if self.save_binary else None,
                
                extraction_method='ebooklib',
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            logger.info(f"DocumentDependency: ebooklib extracted '{result.title}' ({result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"DocumentDependency: ebooklib extraction failed: {e}")
            return DocumentResult(
                file_type='epub',
                binary_content=content if self.save_binary else None,
                extraction_method='ebooklib',
                extraction_successful=False,
                error=f"ebooklib failed: {str(e)}"
            )
    
    def _extract_text_file(self, content: bytes) -> DocumentResult:
        """Extract text from plain text file"""
        try:
            logger.info("DocumentDependency: Processing plain text file")
            
            # Try different encodings
            text = None
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not text:
                raise ValueError("Could not decode text file")
            
            confidence = 0.7 if text and len(text.strip()) > 50 else 0.3
            
            result = DocumentResult(
                text=text.strip() if text else None,
                
                file_type='txt',
                mime_type='text/plain',
                file_size_bytes=len(content),
                
                binary_content=content if self.save_binary else None,
                
                extraction_method='text',
                extraction_successful=True,
                confidence_score=confidence,
            )
            
            logger.info(f"DocumentDependency: Text file extracted ({result.word_count} words)")
            return result
            
        except Exception as e:
            logger.error(f"DocumentDependency: Text extraction failed: {e}")
            return DocumentResult(
                file_type='txt',
                binary_content=content if self.save_binary else None,
                extraction_method='text',
                extraction_successful=False,
                error=f"Text extraction failed: {str(e)}"
            )
    
    async def extract_document(self, fetch_result: FetchResult) -> DocumentResult:
        """
        Download and extract text from a document.
        
        Args:
            fetch_result: Result from FetchDependency containing binary content
            
        Returns:
            DocumentResult with extracted content and metadata
        """
        if not fetch_result or not fetch_result.content:
            return DocumentResult(
                extraction_successful=False,
                error="No content to extract from"
            )
        
        content = fetch_result.content
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        # Detect file type
        file_type, mime_type = self._detect_file_type(fetch_result.url, content)
        
        logger.info(f"DocumentDependency: Processing {file_type} document from {fetch_result.url}")
        
        availability = self._check_dependencies()
        
        # Route to appropriate extractor
        if file_type == 'pdf' and availability.get('pymupdf'):
            result = self._extract_pdf_text(content)
        elif file_type == 'docx' and availability.get('python-docx'):
            result = self._extract_docx_text(content)
        elif file_type == 'epub' and availability.get('ebooklib'):
            result = self._extract_epub_text(content)
        elif file_type == 'txt':
            result = self._extract_text_file(content)
        else:
            # Fallback: try to extract as text
            logger.warning(f"DocumentDependency: No specific handler for {file_type}, trying text extraction")
            result = self._extract_text_file(content)
        
        # Save temporary file if requested
        if self.save_temp_file and result.extraction_successful:
            try:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}')
                temp_file.write(content)
                temp_file.close()
                result.temp_file_path = temp_file.name
                logger.info(f"DocumentDependency: Saved temporary file: {result.temp_file_path}")
            except Exception as e:
                logger.warning(f"DocumentDependency: Could not save temporary file: {e}")
        
        return result


# Export
__all__ = ["DocumentDependency", "DocumentResult"]