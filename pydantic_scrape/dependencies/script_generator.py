"""
Script Generator Dependency - manages script generation with caching and domain lookup
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

from ..agents.script_generator import (
    GeneratedScript,
    ScriptGenDep,
    script_generator_agent,
)
from .fetch import FetchResult


@dataclass
class ScriptLookupKey:
    """Key for looking up cached scripts"""

    domain: str
    extraction_type: str  # e.g., "science_paper", "extract_pdf", "general"
    library: str  # "bs4" or "playwright"

    def to_filename(self) -> str:
        """Convert to a safe filename"""
        safe_domain = self.domain.replace(".", "_").replace("/", "_")
        return f"{safe_domain}_{self.extraction_type}_{self.library}.json"

    def __hash__(self) -> int:
        return hash((self.domain, self.extraction_type, self.library))


@dataclass
class CachedScript:
    """Cached script entry with metadata"""

    script: GeneratedScript
    created_at: str
    source_url: str
    source_html_hash: str
    usage_count: int = 0


class ScriptGeneratorDependency:
    """
    Dependency that handles script generation with intelligent caching.

    Features:
    - Domain-based script lookup
    - Extraction type categorization
    - Script caching to filesystem
    - Usage tracking
    - HTML content hashing for cache validation
    """

    def __init__(
        self,
        cache_dir: str = "./.script_cache",
        model: str = "openai:gpt-4o",
        default_library: str = "bs4",
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.agent = script_generator_agent
        self.default_library = default_library
        self._memory_cache: dict[ScriptLookupKey, CachedScript] = {}

        # Load existing cache into memory
        self._load_cache()

    def _load_cache(self):
        """Load cached scripts from filesystem into memory"""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)

                # Reconstruct key from filename
                parts = cache_file.stem.split("_")
                if len(parts) >= 3:
                    domain = parts[0].replace("_", ".")
                    extraction_type = "_".join(parts[1:-1])
                    library = parts[-1]

                    key = ScriptLookupKey(domain, extraction_type, library)
                    cached_script = CachedScript(
                        script=GeneratedScript(**data["script"]),
                        created_at=data["created_at"],
                        source_url=data["source_url"],
                        source_html_hash=data["source_html_hash"],
                        usage_count=data.get("usage_count", 0),
                    )
                    self._memory_cache[key] = cached_script

            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")

    def _save_cache_entry(self, key: ScriptLookupKey, cached_script: CachedScript):
        """Save a cache entry to filesystem"""
        cache_file = self.cache_dir / key.to_filename()

        data = {
            "script": cached_script.script.model_dump(),
            "created_at": cached_script.created_at,
            "source_url": cached_script.source_url,
            "source_html_hash": cached_script.source_html_hash,
            "usage_count": cached_script.usage_count,
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved script cache: {key.to_filename()}")
        except Exception as e:
            logger.error(f"Failed to save cache entry: {e}")

    def _hash_content(self, content: str) -> str:
        """Create hash of HTML content for cache validation"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            return urlparse(url).netloc.lower()
        except:
            return "unknown"

    async def generate_or_get_script(
        self,
        fetch_result: FetchResult,
        extraction_type: str,
        user_prompt: str,
        library: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> GeneratedScript:
        """
        Get a script for extracting data, using cache when possible.

        Args:
            fetch_result: Result from fetching the page
            extraction_type: Type of extraction (e.g., "science_paper", "extract_pdf")
            user_prompt: What data to extract
            library: Library preference ("bs4" or "playwright")
            force_regenerate: Force regeneration even if cached script exists

        Returns:
            GeneratedScript with code and metadata
        """
        if fetch_result.error or not fetch_result.content:
            raise ValueError(f"Invalid fetch result: {fetch_result.error}")

        library = library or self.default_library
        domain = self._extract_domain(fetch_result.url)
        key = ScriptLookupKey(domain, extraction_type, library)
        content_hash = self._hash_content(fetch_result.content)

        # Check cache first
        if not force_regenerate and key in self._memory_cache:
            cached = self._memory_cache[key]

            # Update usage count
            cached.usage_count += 1
            self._save_cache_entry(key, cached)

            logger.info(
                f"ScriptGeneratorDependency: Using cached script for {domain}/{extraction_type}"
            )
            return cached.script

        # Generate new script
        logger.info(
            f"ScriptGeneratorDependency: Generating new script for {domain}/{extraction_type}"
        )

        agent_result = await self.agent.run(
            user_prompt,
            deps=ScriptGenDep(html_content=fetch_result.content, url=fetch_result.url),
        )

        # Cache the result - extract output from agent result
        from datetime import datetime

        cached_script = CachedScript(
            script=agent_result.output,
            created_at=datetime.now().isoformat(),
            source_url=fetch_result.url,
            source_html_hash=content_hash,
            usage_count=1,
        )

        self._memory_cache[key] = cached_script
        self._save_cache_entry(key, cached_script)

        logger.info(
            f"ScriptGeneratorDependency: Cached new script for {domain}/{extraction_type}"
        )
        return agent_result.output

    def generate_or_get_script_sync(
        self,
        fetch_result: FetchResult,
        extraction_type: str,
        user_prompt: str,
        library: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> GeneratedScript:
        """Synchronous version of generate_or_get_script"""
        if fetch_result.error or not fetch_result.content:
            raise ValueError(f"Invalid fetch result: {fetch_result.error}")

        library = library or self.default_library
        domain = self._extract_domain(fetch_result.url)
        key = ScriptLookupKey(domain, extraction_type, library)
        content_hash = self._hash_content(fetch_result.content)

        # Check cache first
        if not force_regenerate and key in self._memory_cache:
            cached = self._memory_cache[key]

            # Update usage count
            cached.usage_count += 1
            self._save_cache_entry(key, cached)

            logger.info(
                f"ScriptGeneratorDependency: Using cached script for {domain}/{extraction_type}"
            )
            return cached.script

        # Generate new script
        logger.info(
            f"ScriptGeneratorDependency: Generating new script for {domain}/{extraction_type}"
        )

        agent_result = self.agent.run_sync(
            user_prompt,
            deps=ScriptGenDep(html_content=fetch_result.content, url=fetch_result.url),
        )

        # Cache the result - extract output from agent result
        from datetime import datetime

        cached_script = CachedScript(
            script=agent_result.output,
            created_at=datetime.now().isoformat(),
            source_url=fetch_result.url,
            source_html_hash=content_hash,
            usage_count=1,
        )

        self._memory_cache[key] = cached_script
        self._save_cache_entry(key, cached_script)

        logger.info(
            f"ScriptGeneratorDependency: Cached new script for {domain}/{extraction_type}"
        )
        return agent_result.output

    def list_cached_scripts(self) -> list[dict]:
        """List all cached scripts with metadata"""
        results = []
        for key, cached in self._memory_cache.items():
            results.append(
                {
                    "domain": key.domain,
                    "extraction_type": key.extraction_type,
                    "library": key.library,
                    "created_at": cached.created_at,
                    "usage_count": cached.usage_count,
                    "confidence": cached.script.confidence,
                    "target_fields": cached.script.target_fields,
                }
            )
        return results

    def clear_cache(self, domain: Optional[str] = None):
        """Clear cache entries, optionally filtered by domain"""
        if domain:
            # Clear specific domain
            keys_to_remove = [
                k for k in self._memory_cache.keys() if k.domain == domain
            ]
            for key in keys_to_remove:
                del self._memory_cache[key]
                cache_file = self.cache_dir / key.to_filename()
                if cache_file.exists():
                    cache_file.unlink()
            logger.info(f"Cleared cache for domain: {domain}")
        else:
            # Clear all
            self._memory_cache.clear()
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared all script cache")
