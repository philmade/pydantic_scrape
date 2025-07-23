# 🔧 Installation Fix Guide

## Problem
The `lxml[html_clean]` dependency issue and missing API dependencies.

## Solution

### 1. Fix the lxml dependency issue:
```bash
pip uninstall lxml
pip install lxml>=4.9.0 lxml_html_clean>=0.1.0
```

### 2. Install all requirements:
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables:
Make sure you have a `.env` file with:
```bash
GOOGLE_API_KEY="your_google_api_key_here"
GEMINI_API_KEY="your_google_api_key_here"  
OPENAI_API_KEY="your_openai_key_here"
```

### 4. Test the YouTube editor:
```bash
python run_youtube_editor.py
```

## Fixed in requirements.txt:
- ✅ Added `lxml_html_clean>=0.1.0` (separate package)
- ✅ Added `google-generativeai>=0.3.0` (for Gemini)
- ✅ Added `openai>=1.0.0` (for transcription)
- ✅ Removed duplicate `python-dotenv`
- ✅ Removed `flet` (not needed for core functionality)

## API Keys Required:
- **Google API Key**: For Gemini AI video analysis
- **OpenAI API Key**: For Whisper transcription (optional)

The YouTube editing workflow should now work correctly!