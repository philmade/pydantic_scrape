"""YouTube dependency - handles YouTube metadata and subtitle extraction"""

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class YouTubeSubtitle:
    """Individual subtitle entry with timestamp"""
    start_time: float  # seconds
    end_time: float   # seconds
    text: str
    duration: float   # seconds


@dataclass
class YouTubeResult:
    """Result from YouTube metadata and subtitle extraction"""
    
    # Basic video info
    video_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None
    uploader_id: Optional[str] = None
    channel_url: Optional[str] = None
    
    # Video metadata
    duration: Optional[float] = None  # seconds
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: Optional[str] = None
    tags: List[str] = None
    categories: List[str] = None
    
    # Technical details
    resolution: Optional[str] = None
    fps: Optional[float] = None
    format_id: Optional[str] = None
    ext: Optional[str] = None
    
    # Subtitles (rich structured data)
    subtitles_available: bool = False
    subtitle_languages: List[str] = None
    timestamped_subtitles: List[YouTubeSubtitle] = None
    transcript: Optional[str] = None  # Clean transcript without timestamps
    
    # Lookup metadata
    extraction_successful: bool = False
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.categories is None:
            self.categories = []
        if self.subtitle_languages is None:
            self.subtitle_languages = []
        if self.timestamped_subtitles is None:
            self.timestamped_subtitles = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        # Convert subtitle objects to dicts
        result['timestamped_subtitles'] = [
            asdict(sub) for sub in self.timestamped_subtitles
        ]
        return result


class YouTubeDependency:
    """
    Dependency for extracting YouTube metadata and subtitles using yt-dlp.
    
    Provides rich YouTube data extraction including:
    - Complete video metadata
    - Subtitle/SRT data in timestamped format  
    - Clean transcript without timestamps
    """
    
    def __init__(self, extract_subtitles: bool = True, subtitle_lang: str = "en"):
        self.extract_subtitles = extract_subtitles
        self.subtitle_lang = subtitle_lang
        self.required_packages = ["yt-dlp"]
    
    def _check_dependencies(self) -> bool:
        """Check if yt-dlp is available"""
        try:
            import yt_dlp
            return True
        except ImportError as e:
            logger.warning(f"YouTube dependency missing packages: {e}")
            return False
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
            r'youtube\.com/watch\?.*v=([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _parse_subtitles(self, subtitle_data: List[Dict]) -> List[YouTubeSubtitle]:
        """Parse subtitle data into structured format"""
        subtitles = []
        
        for entry in subtitle_data:
            try:
                subtitle = YouTubeSubtitle(
                    start_time=entry.get('start', 0.0),
                    end_time=entry.get('end', 0.0),
                    text=entry.get('text', '').strip(),
                    duration=entry.get('duration', 0.0)
                )
                if subtitle.text:  # Only add non-empty subtitles
                    subtitles.append(subtitle)
            except Exception as e:
                logger.warning(f"Failed to parse subtitle entry: {e}")
                continue
        
        return subtitles
    
    def _create_transcript(self, subtitles: List[YouTubeSubtitle]) -> str:
        """Create clean transcript from timestamped subtitles"""
        if not subtitles:
            return ""
        
        # Join all subtitle text with spaces, removing duplicates
        transcript_parts = []
        last_text = ""
        
        for subtitle in subtitles:
            text = subtitle.text.strip()
            # Remove common subtitle artifacts
            text = re.sub(r'\[.*?\]', '', text)  # Remove [Music], [Applause], etc.
            text = re.sub(r'\(.*?\)', '', text)  # Remove (inaudible), etc.
            text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
            
            if text and text != last_text:  # Avoid duplicates
                transcript_parts.append(text)
                last_text = text
        
        return ' '.join(transcript_parts)
    
    async def extract_metadata(self, url: str) -> YouTubeResult:
        """
        Extract comprehensive YouTube metadata and subtitles.
        
        Args:
            url: YouTube video URL
            
        Returns:
            YouTubeResult with metadata, subtitles, and transcript
        """
        if not self._check_dependencies():
            return YouTubeResult(error="Missing required package: yt-dlp")
        
        video_id = self._extract_video_id(url)
        if not video_id:
            return YouTubeResult(error=f"Could not extract video ID from URL: {url}")
        
        try:
            import yt_dlp
            
            # Configure yt-dlp options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extractaudio': False,
                'format': 'best[height<=720]',  # Don't need high quality for metadata
            }
            
            # Add subtitle extraction options
            if self.extract_subtitles:
                ydl_opts.update({
                    'writesubtitles': True,
                    'writeautomaticsub': True,
                    'subtitleslangs': [self.subtitle_lang, 'en'],  # Prefer specified lang, fallback to English
                    'subtitlesformat': 'json3',  # Get structured subtitle data
                })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract metadata
                logger.info(f"YouTubeDependency: Extracting metadata for {video_id}")
                info = ydl.extract_info(url, download=False)
                
                # Parse basic metadata
                result = YouTubeResult(
                    video_id=video_id,
                    title=info.get('title'),
                    description=info.get('description'),
                    uploader=info.get('uploader'),
                    uploader_id=info.get('uploader_id'), 
                    channel_url=info.get('channel_url'),
                    
                    # Video metadata
                    duration=info.get('duration'),
                    view_count=info.get('view_count'),
                    like_count=info.get('like_count'),
                    upload_date=info.get('upload_date'),
                    tags=info.get('tags', []),
                    categories=info.get('categories', []),
                    
                    # Technical details
                    resolution=f"{info.get('width', 0)}x{info.get('height', 0)}" if info.get('width') else None,
                    fps=info.get('fps'),
                    format_id=info.get('format_id'),
                    ext=info.get('ext'),
                    
                    extraction_successful=True
                )
                
                # Extract subtitles if available
                if self.extract_subtitles and info.get('subtitles'):
                    # Try to get subtitles in preferred language
                    subtitle_info = None
                    for lang in [self.subtitle_lang, 'en', 'en-US']:
                        if lang in info['subtitles']:
                            subtitle_info = info['subtitles'][lang]
                            break
                    
                    # Try automatic subtitles if manual ones not available
                    if not subtitle_info and info.get('automatic_captions'):
                        for lang in [self.subtitle_lang, 'en', 'en-US']:
                            if lang in info['automatic_captions']:
                                subtitle_info = info['automatic_captions'][lang]
                                break
                    
                    if subtitle_info:
                        # Get JSON3 format for structured data
                        json3_format = None
                        for fmt in subtitle_info:
                            if fmt.get('ext') == 'json3':
                                json3_format = fmt
                                break
                        
                        if json3_format:
                            try:
                                # Download subtitle data
                                subtitle_data = ydl.urlopen(json3_format['url']).read()
                                import json
                                subtitle_json = json.loads(subtitle_data)
                                
                                # Parse subtitle events
                                events = subtitle_json.get('events', [])
                                subtitle_entries = []
                                
                                for event in events:
                                    if 'segs' in event:
                                        start_time = event.get('tStartMs', 0) / 1000.0
                                        duration = event.get('dDurationMs', 0) / 1000.0
                                        end_time = start_time + duration
                                        
                                        text_parts = []
                                        for seg in event['segs']:
                                            if 'utf8' in seg:
                                                text_parts.append(seg['utf8'])
                                        
                                        if text_parts:
                                            subtitle_entries.append({
                                                'start': start_time,
                                                'end': end_time,
                                                'duration': duration,
                                                'text': ''.join(text_parts)
                                            })
                                
                                # Convert to structured subtitles
                                result.timestamped_subtitles = self._parse_subtitles(subtitle_entries)
                                result.transcript = self._create_transcript(result.timestamped_subtitles)
                                result.subtitles_available = len(result.timestamped_subtitles) > 0
                                result.subtitle_languages = list(info.get('subtitles', {}).keys())
                                
                                logger.info(f"YouTubeDependency: Extracted {len(result.timestamped_subtitles)} subtitle entries")
                                
                            except Exception as e:
                                logger.error(f"Failed to parse subtitles: {e}")
                
                logger.info(f"YouTubeDependency: Successfully extracted metadata for '{result.title}'")
                return result
                
        except Exception as e:
            logger.error(f"YouTubeDependency: Extraction failed: {e}")
            return YouTubeResult(
                video_id=video_id,
                error=f"YouTube extraction failed: {str(e)}"
            )


# Export
__all__ = ["YouTubeDependency", "YouTubeResult", "YouTubeSubtitle"]