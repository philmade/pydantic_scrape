# Installation Guide

This guide explains how to install pydantic-scrape with different dependency configurations.

## Quick Start (All Features)

For full functionality including YouTube processing, document handling, and academic research:

```bash
pip install pydantic-scrape
```

## PyPI Installation with Optional Dependencies

Currently, due to the package's architecture with unconditional imports, all major dependencies are required. However, the package supports these installation patterns:

### Standard Installation
```bash
pip install pydantic-scrape
```

### Development Installation  
```bash
pip install pydantic-scrape[dev]
```

**Development extras include:**
- pytest (testing framework)
- black (code formatting)
- ruff (linting) 
- build & twine (packaging tools)

## Local Development with Requirements Files

For local development and testing, you can use the modular requirements files:

### Core Scraping (Local Development)
```bash
pip install -r requirements-core.txt
```

### Academic Research Extensions (Local Development)
```bash  
pip install -r requirements-academic.txt
```

### YouTube Processing (Local Development)
```bash
pip install -r requirements-youtube.txt
```

### Document Processing (Local Development)
```bash
pip install -r requirements-documents.txt
```

**Note:** Due to current architecture constraints with unconditional imports, most functionality requires the full dependency set. Future versions will support truly optional dependencies.

## Testing Your Installation

After installation, test that the package imports correctly:

```python
import pydantic_scrape
from pydantic_scrape.dependencies.fetch import fetch_url

print("✅ Installation successful!")
print(f"Version: {pydantic_scrape.__version__}")
```

## Fresh Installation Test

To test that the package installs correctly from scratch:

```bash
# Remove existing environment
rm -rf .venv

# Create fresh environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install and test
pip install -r requirements-core.txt
python -c "import pydantic_scrape; print('✅ Success!')"
```

## Dependency Overview

### Core Framework
- **pydantic-ai**: Agent framework
- **pydantic-graph**: Graph execution engine  
- **camoufox**: Browser automation
- **newspaper3k**: Article extraction
- **beautifulsoup4**: HTML parsing

### Document Processing
- **PyMuPDF**: PDF processing
- **python-docx**: Word documents
- **EbookLib**: EPUB files

### YouTube & Video
- **yt-dlp**: Video downloading
- **openai**: Transcription services
- **google-generativeai**: AI video analysis

### Academic Research
- **pyalex**: OpenAlex database access
- **habanero**: Crossref metadata
- **searchthescience**: Scientific search (optional)

## Missing Dependencies Fixed

The following dependencies were missing from the original requirements.txt and have been added:

- `httpx>=0.24.0` - HTTP client used by fetch.py
- `platformdirs>=3.0.0` - Cross-platform cache directories
- `searchthescience>=1.0.0` - Scientific search functionality

## Architecture Notes

The package imports all major dependencies unconditionally in its `__init__.py` files, so the "core" vs "optional" distinction is primarily for understanding the codebase structure rather than true optional installations. All dependencies listed in requirements-core.txt are effectively required for the package to import successfully.