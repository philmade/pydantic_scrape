
import os
import re
from pathlib import Path
import yt_dlp
from loguru import logger
from platformdirs import user_cache_dir

def get_default_cache_dir() -> Path:
    """Returns the platform-specific user cache directory for the app."""
    return Path(user_cache_dir("pydantic-scrape", "PhillM"))

class DownloadService:
    """A service for downloading videos and creating project workspaces in a central cache."""

    def __init__(self, base_output_dir: str = None):
        """Initializes the service, setting up the cache directory."""
        if base_output_dir:
            self.base_output_dir = Path(base_output_dir)
        else:
            self.base_output_dir = get_default_cache_dir()
        
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using cache/output directory: {self.base_output_dir}")

    def get_video_info(self, youtube_url: str) -> dict:
        """Extracts video information without downloading the video."""
        browsers_to_try = ["chrome", "firefox", "brave", "edge", "safari"]
        for browser in browsers_to_try:
            try:
                logger.info(f"Attempting to get video info using cookies from '{browser}'...")
                ydl_opts_info = {
                    "quiet": True,
                    "extract_flat": True,
                    "cookiesfrombrowser": (browser,), # Must be a tuple
                }
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    logger.success(f"Successfully got video info using '{browser}' cookies.")
                    return info
            except Exception as e:
                logger.warning(f"Could not get video info with '{browser}': {e}")
        
        logger.error("All attempts to get video info with browser cookies failed.")
        raise RuntimeError("Failed to get video info from YouTube. Please ensure you are logged into YouTube in a supported browser (Chrome, Firefox, etc.).")

    def sanitize_filename(self, name: str) -> str:
        """Remove illegal characters from a string so it can be a valid filename."""
        return re.sub(r'[<>:"/\\|?*]', "_", name)

    def create_project_workspace(self, youtube_url: str) -> Path:
        """
        Creates a namespaced directory for a new video project using the YouTube video ID.
        If the directory already exists, it returns the existing path.
        Saves the video title to a text file for user reference.
        """
        logger.info(f"Fetching video info for: {youtube_url}")
        video_info = self.get_video_info(youtube_url)
        video_id = video_info.get("id", None)
        if not video_id:
            raise ValueError("Could not extract video ID from YouTube URL.")

        project_dir = self.base_output_dir / video_id
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Save title for user reference
        title_path = project_dir / "title.txt"
        if not title_path.exists():
            video_title = video_info.get("title", "untitled_video")
            with open(title_path, "w") as f:
                f.write(video_title)

        logger.info(f"Project workspace ready: {project_dir}")
        return project_dir

    def download_video(self, youtube_url: str, project_dir: Path) -> str:
        """Downloads the video from a YouTube URL into the project directory if it doesn't exist."""
        # Check if a video file already exists in the project directory
        existing_videos = list(project_dir.glob("*.mp4")) + list(project_dir.glob("*.webm"))
        if existing_videos:
            logger.info(f"Using existing cached video: {existing_videos[0]}")
            return str(existing_videos[0])

        logger.info(f"No cached video found. Downloading from {youtube_url}...")
        video_path_template = str(project_dir / "%(title)s.%(ext)s")

        browsers_to_try = ["chrome", "firefox", "brave", "edge", "safari"]
        for browser in browsers_to_try:
            try:
                logger.info(f"Attempting to download video using cookies from '{browser}'...")
                ydl_opts = {
                    "format": "best[height<=720][ext=mp4]/best[height<=720]",
                    "outtmpl": video_path_template,
                    "prefer_ffmpeg": True,
                    "postprocessors": [
                        {
                            "key": "FFmpegVideoConvertor",
                            "preferedformat": "mp4",
                        }
                    ],
                    "quiet": True,
                    "cookiesfrombrowser": (browser,), # Must be a tuple
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(youtube_url, download=True)
                    logger.success(f"Successfully downloaded video using '{browser}' cookies.")
                    # After download, find the actual file path
                    downloaded_files = list(project_dir.glob(f"{self.sanitize_filename(info_dict['title'])}"))
                    if downloaded_files:
                        return str(downloaded_files[0])
                    else:
                        return ydl.prepare_filename(info_dict)
            except Exception as e:
                logger.warning(f"Could not download video with '{browser}': {e}")

        logger.error("All attempts to download video with browser cookies failed.")
        raise RuntimeError("Failed to download video from YouTube. Please ensure you are logged into YouTube in a supported browser (Chrome, Firefox, etc.).")
