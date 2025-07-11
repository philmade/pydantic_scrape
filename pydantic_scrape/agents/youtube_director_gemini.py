from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv
from google import genai as google_genai
from google.genai.types import HttpOptions, Part
from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent

load_dotenv()


class EditClip(BaseModel):
    """A single edit clip with timecode in/out and the selected phrase"""

    timecode_in: str  # Format: "HH:MM:SS,mmm"
    timecode_out: str  # Format: "HH:MM:SS,mmm"
    phrase: str  # The exact phrase from the transcript


class EditScript(BaseModel):
    """A complete edit script containing multiple clips"""

    clips: List[EditClip]


@dataclass
class YouTubeDirectorContext:
    """Context for YouTube director agent"""

    youtube_url: str
    brief: str
    transcript_text: str = None
    srt_data: str = None


# YouTube Director Agent using Pydantic AI
youtube_director_agent = Agent(
    "google-gla:gemini-2.5-pro",
    deps_type=YouTubeDirectorContext,
    output_type=EditScript,
    system_prompt="""You are an expert documentary film editor. Your task is to create a structured edit script by selecting key phrases from a provided transcript with precise timecodes.

You will analyze video content and transcript to identify the most compelling moments suitable for an edit based on the creative brief.

Return an EditScript with clips that have:
- timecode_in: Start time in HH:MM:SS,mmm format
- timecode_out: End time in HH:MM:SS,mmm format
- phrase: Exact phrase from the transcript

Select only the most essential moments that align with the creative brief.""",
)


# @youtube_director_agent.tool
# async def access_srt_data(
#     ctx: RunContext[YouTubeDirectorContext],
# ) -> str:
#     """Access the SRT-like file data for making editing decisions"""
#     if ctx.deps.srt_data:
#         return f"SRT Data:\n{ctx.deps.srt_data}"
#     return "No SRT data available"


# @youtube_director_agent.tool
# async def access_transcript(
#     ctx: RunContext[YouTubeDirectorContext],
# ) -> str:
#     """Access the transcript text for reference"""
#     if ctx.deps.transcript_text:
#         return f"Transcript:\n{ctx.deps.transcript_text}"
#     return "No transcript available"


async def get_creative_edit_from_video(
    youtube_url: str,
    brief: str,
) -> EditScript | None:
    """
    Uses direct Google Gemini API with video analysis to create structured edit script.
    This function can actually analyze YouTube videos directly.
    """
    logger.info("Using Google Gemini API directly for video analysis...")
    try:
        # Use the direct Google Gemini API client for video analysis
        client = google_genai.Client(http_options=HttpOptions(api_version="v1beta"))
        model_id = "gemini-2.5-pro"
        # Create structured prompt for edit script
        prompt = f"""
You are an expert documentary film editor. Analyze this video and create a structured edit script.

**Creative Brief:**
{brief}

**Instructions:**
1. Watch the video carefully to understand the story, pacing, and visuals
2. Select key moments that align with the creative brief
3. For each selected moment, provide accurate timecodes and the exact phrase spoken
4. Return ONLY a JSON object in this exact format:

{{
  "clips": [
    {{
      "timecode_in": "HH:MM:SS,mmm",
      "timecode_out": "HH:MM:SS,mmm",
      "phrase": "exact phrase from the video"
    }}
  ]
}}

Select 3-8 of the most compelling moments that tell the story effectively.
"""
        # Make the API call with video analysis - use exact format from working example
        response = client.models.generate_content(
            model=model_id,
            contents=[
                Part.from_uri(
                    file_uri=youtube_url,
                    mime_type="video/mp4",
                ),
                prompt,
            ],
        )
        logger.info(f"Raw Gemini response: {response.text}")

        # Parse the JSON response
        import json

        try:
            # Extract JSON from response
            response_text = response.text.strip()
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.rfind("```")
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text
            # Parse and validate
            data = json.loads(json_str)
            
            # Fix common JSON response errors before validation
            if "clips" in data:
                for clip in data["clips"]:
                    # Fix typo: "time_out" should be "timecode_out" 
                    if "time_out" in clip and "timecode_out" not in clip:
                        clip["timecode_out"] = clip.pop("time_out")
                        logger.warning("Fixed typo: 'time_out' -> 'timecode_out' in Gemini response")
            
            edit_script = EditScript.model_validate(data)
            logger.success("Successfully received edit script from Google Gemini API.")
            return edit_script
        except (json.JSONDecodeError, Exception) as parse_error:
            logger.error(f"Failed to parse response: {parse_error}")
            logger.error(f"Response text: {response.text}")
            return None
    except Exception as e:
        logger.error(f"An error occurred while calling the Google Gemini API: {e}")
        import traceback

        traceback.print_exc()
        return None


async def get_creative_edit_from_text(
    youtube_url: str,
    brief: str,
    transcript_text: str = None,
) -> EditScript | None:
    """
    Uses Pydantic AI agent with transcript text (no video analysis).
    Falls back to direct video analysis if no transcript provided.
    """
    if not transcript_text:
        logger.info("No transcript provided, falling back to direct video analysis...")
        return await get_creative_edit_from_video(youtube_url, brief)

    logger.info("Using Pydantic AI agent for creative edit from text...")
    try:
        context = YouTubeDirectorContext(
            youtube_url=youtube_url, brief=brief, transcript_text=transcript_text
        )

        prompt = f"""
Analyze the provided transcript and create an edit script based on this creative brief:

**Creative Brief:**
{brief}

**Available Data:**
- YouTube URL: {youtube_url}
- Transcript: {transcript_text[:500]}...

**Instructions:**
1. Select key phrases from the transcript that align with the creative brief
2. For each selected phrase, estimate reasonable timecodes based on context
3. Return a structured EditScript with clips containing timecode_in, timecode_out, and the exact phrase

Focus on the most compelling moments that tell the story effectively.
"""

        result = await youtube_director_agent.run(prompt, deps=context)
        logger.success("Successfully received edit script from Pydantic AI agent.")
        return result.output

    except Exception as e:
        logger.error(f"An error occurred while calling the Pydantic AI agent: {e}")
        import traceback

        traceback.print_exc()
        return None


# Alias for backward compatibility
async def get_gemini_paper_edit_srt(
    youtube_url: str, brief: str, srt_data: str = None
) -> EditScript | None:
    """
    Legacy function name - redirects to video analysis.
    Note: srt_data parameter is ignored for backward compatibility.
    """
    return await get_creative_edit_from_video(youtube_url, brief)
