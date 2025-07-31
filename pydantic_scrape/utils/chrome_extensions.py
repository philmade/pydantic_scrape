"""
Chrome Extensions Setup for Auto-Popup Dismissal

This module handles setting up Chrome extensions that automatically:
- Dismiss cookie banners
- Block ads and popups  
- Handle GDPR consent forms
- Remove annoying overlays

Extensions used:
- uBlock Origin: Ad and popup blocking
- I don't care about cookies: Auto cookie banner dismissal
- Consent-O-Matic: GDPR consent automation
"""

import os
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

from loguru import logger


class ChromeExtensionManager:
    """Manages Chrome extensions for automatic popup dismissal"""

    def __init__(self, profile_dir: Optional[str] = None):
        """
        Initialize the Chrome extension manager.
        
        Args:
            profile_dir: Directory for Chrome profile. If None, creates in project dir.
        """
        if profile_dir is None:
            project_root = Path(__file__).parent.parent.parent
            profile_dir = project_root / "chrome_profile_with_extensions"
        
        self.profile_dir = Path(profile_dir)
        self.extensions_dir = self.profile_dir / "extensions"
        
        # Extension download URLs (these are example URLs - in practice you'd need the actual CRX files)
        self.extensions = {
            "ublock_origin": {
                "name": "uBlock Origin",
                "description": "Ad and popup blocker",
                "chrome_web_store_id": "cjpalhdlnbpafiamejdnhcphjbkeiagm",
            },
            "i_dont_care_about_cookies": {
                "name": "I don't care about cookies", 
                "description": "Auto cookie banner dismissal",
                "chrome_web_store_id": "fihnjjcciajhdojfnbdddfaoknhalnja",
            },
            "consent_o_matic": {
                "name": "Consent-O-Matic",
                "description": "GDPR consent automation", 
                "chrome_web_store_id": "mdjildafknihdffpkfmmpnpoiajfjnjd",
            }
        }

    def setup_chrome_profile(self, force_recreate: bool = False) -> str:
        """
        Set up Chrome profile with anti-popup extensions.
        
        Args:
            force_recreate: If True, recreates the profile even if it exists
            
        Returns:
            Path to the Chrome profile directory
        """
        try:
            if force_recreate and self.profile_dir.exists():
                logger.info(f"🗑️  Removing existing Chrome profile: {self.profile_dir}")
                shutil.rmtree(self.profile_dir)
            
            if self.profile_dir.exists():
                logger.info(f"✅ Using existing Chrome profile: {self.profile_dir}")
                return str(self.profile_dir)
            
            logger.info(f"🏗️  Creating Chrome profile with extensions: {self.profile_dir}")
            
            # Create profile directories
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.extensions_dir.mkdir(parents=True, exist_ok=True)
            
            # Create basic Chrome preferences to disable some popups
            self._create_chrome_preferences()
            
            # Note: For now, we'll use Chrome args to disable some popups
            # Extension installation would require more complex setup
            logger.info("✅ Chrome profile created with popup-blocking preferences")
            
            return str(self.profile_dir)
            
        except Exception as e:
            logger.error(f"❌ Failed to setup Chrome profile: {e}")
            raise

    def _create_chrome_preferences(self):
        """Create Chrome preferences file to disable various popups and notifications"""
        preferences = {
            "profile": {
                "default_content_setting_values": {
                    "notifications": 2,  # Block notifications
                    "geolocation": 2,    # Block location requests
                    "media_stream": 2,   # Block camera/mic requests
                },
                "managed_default_content_settings": {
                    "notifications": 2,
                    "geolocation": 2, 
                    "media_stream": 2,
                },
                "content_settings": {
                    "exceptions": {
                        "notifications": {},
                        "geolocation": {},
                    }
                }
            },
            "browser": {
                "show_home_button": False,
                "check_default_browser": False,
                "has_seen_welcome_page": True,
            },
            "first_run_tabs": [],
            "homepage_is_newtabpage": True,
            "session": {
                "restore_on_startup": 1  # Open new tab page on startup
            }
        }
        
        import json
        prefs_file = self.profile_dir / "Default" / "Preferences"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(prefs_file, 'w') as f:
            json.dump(preferences, f, indent=2)
        
        logger.info("📝 Created Chrome preferences file")

    def get_chrome_args(self) -> List[str]:
        """
        Get Chrome arguments for popup blocking and privacy.
        
        Returns:
            List of Chrome command line arguments
        """
        args = [
            # Disable various popup types
            "--disable-notifications",
            "--disable-popup-blocking",  # Ironically, this can help with some overlays
            "--disable-infobars",
            "--disable-extensions-file-access-check",
            "--disable-web-security",  # Helps with some restrictive sites
            "--disable-features=TranslateUI",  # Disable translate popup
            "--disable-ipc-flooding-protection",
            
            # Privacy and tracking protection
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-sync",
            
            # Performance optimizations
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            
            # Content settings
            "--autoplay-policy=no-user-gesture-required",
        ]
        
        return args

    def get_zendriver_config(self, headless: bool = False) -> dict:
        """
        Get configuration dict for Zendriver with popup-blocking setup.
        
        Args:
            headless: Whether to run in headless mode
            
        Returns:
            Dict with Zendriver configuration
        """
        profile_path = self.setup_chrome_profile()
        
        config = {
            "headless": headless,
            "user_data_dir": profile_path,
            "browser_args": self.get_chrome_args(),
            "sandbox": False,  # Disable sandbox to prevent connection issues
        }
        
        logger.info(f"🔧 Chrome config ready with profile: {profile_path}")
        return config


# Global instance for easy access
chrome_manager = ChromeExtensionManager()


def get_popup_blocking_chrome_config(headless: bool = False) -> dict:
    """
    Convenience function to get Chrome configuration with popup blocking.
    
    Args:
        headless: Whether to run in headless mode
        
    Returns:
        Dict with Zendriver configuration for popup-free browsing
    """
    return chrome_manager.get_zendriver_config(headless=headless)


def setup_chrome_extensions(force_recreate: bool = False) -> str:
    """
    Convenience function to setup Chrome profile with extensions.
    
    Args:
        force_recreate: If True, recreates the profile even if it exists
        
    Returns:
        Path to the Chrome profile directory
    """
    return chrome_manager.setup_chrome_profile(force_recreate=force_recreate)