"""
YouTube Editor Graph - Complete workflow for AI-powered YouTube video editing

This graph orchestrates the full workflow:
1. Generate edit script using YouTube Director Agent (with caching)
2. Download YouTube video using yt-dlp
3. Import into DaVinci Resolve and perform cuts
"""

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from pydantic_scrape.agents.youtube_director_gemini import (
    EditScript,
    get_creative_edit_from_video,
)


def extract_youtube_video_id(url: str) -> str:
    """Extract YouTube video ID from URL"""
    # Handle various YouTube URL formats
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    # Fallback to UUID if we can't extract the ID
    logger.warning(f"Could not extract video ID from URL: {url}, using random ID")
    return str(uuid.uuid4())[:8]


@dataclass
class YouTubeEditorState:
    """State for the complete YouTube editing workflow"""

    # Input parameters
    youtube_url: str
    brief: str

    # Project management
    project_uid: str = None
    project_dir: Path = None

    # Processing state
    edit_script: Optional[EditScript] = None
    edit_script_path: Optional[str] = None
    video_path: Optional[str] = None

    # DaVinci integration
    davinci_script_path: Optional[str] = None
    timeline_created: bool = False

    # Status tracking
    start_time: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.project_uid is None:
            self.project_uid = extract_youtube_video_id(self.youtube_url)
        if self.start_time == 0.0:
            self.start_time = time.time()


@dataclass
class YouTubeEditorDeps:
    """Dependencies for YouTube Editor workflow"""

    video_projects_dir: str = "./video_projects"
    cache_edit_scripts: bool = True
    download_video: bool = True
    create_final_edit: bool = True
    enhanced_subtitles: bool = False


class GenerateEditScriptNode(
    BaseNode[YouTubeEditorState, YouTubeEditorDeps, "DownloadVideoNode"]
):
    """Node to generate edit script using YouTube Director Agent with caching"""

    async def run(
        self, ctx: GraphRunContext[YouTubeEditorState, YouTubeEditorDeps]
    ) -> "DownloadVideoNode":
        logger.info("GenerateEditScriptNode: Starting edit script generation")

        try:
            # Set up project directory
            ctx.state.project_dir = (
                Path(ctx.deps.video_projects_dir) / ctx.state.project_uid
            )
            ctx.state.project_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Project directory: {ctx.state.project_dir}")

            # Check for cached edit script
            cache_path = ctx.state.project_dir / "edit_script.json"

            if ctx.deps.cache_edit_scripts and cache_path.exists():
                logger.info("Found cached edit script, loading...")
                try:
                    with open(cache_path, "r") as f:
                        cached_data = json.load(f)
                    ctx.state.edit_script = EditScript.model_validate(cached_data)
                    ctx.state.edit_script_path = str(cache_path)
                    logger.info(
                        f"Loaded cached edit script with {len(ctx.state.edit_script.clips)} clips"
                    )
                    return DownloadVideoNode()
                except Exception as e:
                    logger.warning(f"Failed to load cached edit script: {e}")

            # Generate new edit script using YouTube Director Agent
            logger.info("Calling YouTube Director Agent...")
            edit_script = await get_creative_edit_from_video(
                youtube_url=ctx.state.youtube_url, brief=ctx.state.brief
            )

            if not edit_script:
                raise ValueError("YouTube Director Agent returned no edit script")

            ctx.state.edit_script = edit_script

            # Log the generated script for validation
            logger.info("Generated edit script summary:")
            for i, clip in enumerate(edit_script.clips, 1):
                logger.info(f"  Clip {i}: {clip.timecode_in} -> {clip.timecode_out}")
                logger.info(
                    f"    Phrase: {clip.phrase[:100]}{'...' if len(clip.phrase) > 100 else ''}"
                )

            # Validate total duration makes sense
            if len(edit_script.clips) > 0:
                first_clip_start = CreateFFmpegEditNode()._timecode_to_seconds(
                    edit_script.clips[0].timecode_in
                )
                last_clip_end = CreateFFmpegEditNode()._timecode_to_seconds(
                    edit_script.clips[-1].timecode_out
                )
                logger.info(
                    f"Edit spans from {first_clip_start:.1f}s to {last_clip_end:.1f}s"
                )

            # Cache the edit script
            if ctx.deps.cache_edit_scripts:
                with open(cache_path, "w") as f:
                    json.dump(edit_script.model_dump(), f, indent=2)
                ctx.state.edit_script_path = str(cache_path)
                logger.info(f"Cached edit script to: {cache_path}")

            logger.info(f"Generated edit script with {len(edit_script.clips)} clips")
            return DownloadVideoNode()

        except Exception as e:
            ctx.state.error = f"Edit script generation failed: {e}"
            logger.error(ctx.state.error)
            return End({"success": False, "error": ctx.state.error})


class DownloadVideoNode(
    BaseNode[YouTubeEditorState, YouTubeEditorDeps, "CreateFFmpegEditNode"]
):
    """Node to download YouTube video using yt-dlp"""

    async def run(
        self, ctx: GraphRunContext[YouTubeEditorState, YouTubeEditorDeps]
    ) -> "CreateFFmpegEditNode":
        logger.info("DownloadVideoNode: Starting video download")

        try:
            if not ctx.deps.download_video:
                logger.info("Video download disabled, skipping...")
                return CreateFFmpegEditNode()

            # Check if video already exists
            downloads_dir = ctx.state.project_dir / "downloads"
            downloads_dir.mkdir(exist_ok=True)

            # Look for existing video file (check multiple formats)
            video_patterns = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov"]
            for pattern in video_patterns:
                for video_file in downloads_dir.glob(pattern):
                    ctx.state.video_path = str(video_file)
                    logger.info(f"Found existing video: {video_file}")
                    return CreateFFmpegEditNode()

            # Download video using yt-dlp
            logger.info(f"Downloading video from: {ctx.state.youtube_url}")
            logger.info(f"Downloads directory: {downloads_dir}")

            # Use absolute path for output template with video ID
            output_template = str(
                downloads_dir.absolute() / f"{ctx.state.project_uid}.%(ext)s"
            )
            logger.info(f"Output template: {output_template}")

            cmd = [
                "yt-dlp",
                "--format",
                "best[height<=720]",  # Reasonable quality for editing
                "--output",
                output_template,
                "--no-playlist",
                "--verbose",  # Add verbose for debugging
                ctx.state.youtube_url,
            ]

            logger.info(f"Running: {' '.join(cmd)}")
            logger.info(f"Working directory: {ctx.state.project_dir}")

            # Run from the downloads directory itself for better path handling
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(downloads_dir)
            )

            logger.info(f"yt-dlp return code: {result.returncode}")

            if result.stdout:
                logger.info(f"yt-dlp stdout: {result.stdout}")
            if result.stderr:
                logger.info(f"yt-dlp stderr: {result.stderr}")

            if result.returncode != 0:
                raise RuntimeError(
                    f"yt-dlp failed with return code {result.returncode}: {result.stderr}"
                )

            logger.info("yt-dlp completed successfully")

            # Find the downloaded file (check multiple extensions and patterns)
            video_patterns = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov"]
            found_file = None

            # Wait a moment for file system to update
            import time

            time.sleep(0.5)

            for pattern in video_patterns:
                files = list(downloads_dir.glob(pattern))
                logger.info(f"Looking for pattern {pattern}: found {len(files)} files")
                if files:
                    found_file = files[0]  # Take the first match
                    break

            if found_file:
                ctx.state.video_path = str(found_file)
                logger.info(f"Downloaded video to: {found_file}")
                logger.info(
                    f"File size: {found_file.stat().st_size / (1024 * 1024):.1f} MB"
                )
            else:
                # List all files in downloads directory for debugging
                all_files = list(downloads_dir.glob("*"))
                logger.error(f"No video files found in {downloads_dir}")
                logger.error(
                    f"All files in downloads directory: {[f.name for f in all_files]}"
                )
                logger.error(f"Checking absolute path: {downloads_dir.absolute()}")
                raise FileNotFoundError(
                    f"Downloaded video file not found in {downloads_dir}"
                )

            return CreateFFmpegEditNode()

        except Exception as e:
            ctx.state.error = f"Video download failed: {e}"
            logger.error(ctx.state.error)
            return End({"success": False, "error": ctx.state.error})


class CreateFFmpegEditNode(BaseNode[YouTubeEditorState, YouTubeEditorDeps, End]):
    """Node to create final edit using FFmpeg"""

    async def run(
        self, ctx: GraphRunContext[YouTubeEditorState, YouTubeEditorDeps]
    ) -> End:
        logger.info("CreateFFmpegEditNode: Starting FFmpeg edit creation")

        try:
            if not ctx.deps.create_final_edit:
                logger.info("FFmpeg editing disabled, workflow complete")
                return End(
                    {
                        "success": True,
                        "message": "YouTube Editor workflow completed",
                        "project_dir": str(ctx.state.project_dir),
                        "edit_script_path": ctx.state.edit_script_path,
                        "video_path": ctx.state.video_path,
                        "processing_time": time.time() - ctx.state.start_time,
                    }
                )

            # Create FFmpeg edit using the edit script (for sense-checking)
            output_path = ctx.state.project_dir / "final_edit.mp4"
            ffmpeg_result = self._create_ffmpeg_edit(
                ctx.state.edit_script, ctx.state.video_path, output_path
            )

            if ffmpeg_result["success"]:
                logger.info(f"Successfully created FFmpeg edit: {output_path}")
            else:
                logger.warning(f"FFmpeg edit had issues: {ffmpeg_result.get('message')}")

            # Also create DaVinci Resolve import
            davinci_result = self._create_davinci_import(
                ctx.state.edit_script, ctx.state.video_path, ctx.state.project_dir, ctx.deps.enhanced_subtitles
            )

            if davinci_result["success"]:
                ctx.state.timeline_created = True
                logger.info("Successfully imported to DaVinci Resolve")
            else:
                logger.warning(f"DaVinci import had issues: {davinci_result.get('message')}")

            return End(
                {
                    "success": True,
                    "message": "YouTube Editor workflow completed",
                    "project_dir": str(ctx.state.project_dir),
                    "edit_script_path": ctx.state.edit_script_path,
                    "video_path": ctx.state.video_path,
                    "final_edit_path": str(output_path) if ffmpeg_result["success"] else None,
                    "edit_created": ctx.state.timeline_created,
                    "processing_time": time.time() - ctx.state.start_time,
                    "ffmpeg_result": ffmpeg_result,
                    "davinci_result": davinci_result,
                }
            )

        except Exception as e:
            ctx.state.error = f"FFmpeg edit creation failed: {e}"
            logger.error(ctx.state.error)
            return End({"success": False, "error": ctx.state.error})

    def _create_ffmpeg_edit(
        self, edit_script: EditScript, video_path: str, output_path: Path
    ) -> Dict[str, Any]:
        """Create final edit using FFmpeg"""
        try:
            logger.info(f"Creating FFmpeg edit with {len(edit_script.clips)} clips")

            # Create a filter_complex for concatenating the clips
            filter_parts = []
            input_parts = []

            for i, clip in enumerate(edit_script.clips):
                start_seconds = self._timecode_to_seconds(clip.timecode_in)
                end_seconds = self._timecode_to_seconds(clip.timecode_out)

                # Skip clips with invalid timecodes
                if end_seconds <= start_seconds:
                    logger.warning(
                        f"Skipping clip {i + 1} with invalid timecode: {clip.timecode_in} -> {clip.timecode_out}"
                    )
                    continue

                duration = end_seconds - start_seconds

                # Create a filter to extract this segment
                filter_parts.append(
                    f"[0:v]trim=start={start_seconds}:duration={duration},setpts=PTS-STARTPTS[v{i}]"
                )
                filter_parts.append(
                    f"[0:a]atrim=start={start_seconds}:duration={duration},asetpts=PTS-STARTPTS[a{i}]"
                )
                input_parts.append(f"[v{i}][a{i}]")

                logger.info(
                    f"Clip {i + 1}: {clip.phrase} ({start_seconds:.2f}s - {end_seconds:.2f}s, duration: {duration:.2f}s)"
                )

            if not input_parts:
                return {"success": False, "message": "No valid clips to process"}

            # Concatenate all the clips
            concat_filter = (
                f"{''.join(input_parts)}concat=n={len(input_parts)}:v=1:a=1[outv][outa]"
            )

            # Complete filter complex
            filter_complex = ";".join(filter_parts + [concat_filter])

            # FFmpeg command - use absolute paths
            cmd = [
                "ffmpeg",
                "-i",
                str(Path(video_path).absolute()),
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-map",
                "[outa]",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-y",  # Overwrite output file
                str(output_path.absolute()),
            ]

            logger.info(f"Running FFmpeg: {' '.join(cmd[:10])}... (truncated)")
            logger.info(f"Output will be saved to: {output_path}")

            # Run FFmpeg
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(output_path.parent)
            )

            if result.returncode == 0:
                file_size = output_path.stat().st_size / (1024 * 1024)  # MB
                logger.info(
                    f"FFmpeg completed successfully. Output file size: {file_size:.1f} MB"
                )
                return {
                    "success": True,
                    "message": "FFmpeg edit created successfully",
                    "output_path": str(output_path),
                    "file_size_mb": file_size,
                    "clips_processed": len(input_parts),
                }
            else:
                logger.error(f"FFmpeg failed with return code {result.returncode}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                return {
                    "success": False,
                    "message": f"FFmpeg failed with return code {result.returncode}",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }

        except Exception as e:
            return {"success": False, "message": f"Failed to create FFmpeg edit: {e}"}

    def _create_davinci_import(
        self, edit_script: EditScript, video_path: str, project_dir: Path, enhanced_subtitles: bool = False
    ) -> Dict[str, Any]:
        """Create multiple import options for professional editing workflows"""
        try:
            logger.info("Creating professional editing workflow files...")
            
            # 1. Create EDL file (industry standard)
            edl_result = self._create_edl_export(edit_script, video_path, project_dir)
            
            # 2. Create XML files (with subtitle support)
            xml_result = self._create_xml_export(edit_script, video_path, project_dir, enhanced_subtitles)
            
            # 3. Create DaVinci JSON script (backup)
            davinci_script = self._convert_to_davinci_format(edit_script, video_path)
            davinci_script_path = project_dir / "davinci_script.json"
            with open(davinci_script_path, "w") as f:
                json.dump(davinci_script, f, indent=2)
            
            # 4. Create comprehensive import instructions
            instructions_path = project_dir / "IMPORT_INSTRUCTIONS.txt"
            self._create_import_instructions(instructions_path, video_path, edl_result.get("edl_path"), xml_result)
            
            logger.info("Created multiple import options for professional workflow")
            
            # Try DaVinci import if requested, but don't fail if it doesn't work
            davinci_result = {"success": True, "message": "Professional editing files created"}
            if enhanced_subtitles:
                logger.info("Enhanced subtitles requested - attempting DaVinci import...")
                davinci_result = self._run_davinci_import(str(davinci_script_path), str(project_dir), enhanced_subtitles)
            
            # Combine results
            return {
                "success": True,
                "message": "Professional editing workflow created",
                "edl_created": edl_result.get("success", False),
                "edl_path": edl_result.get("edl_path"),
                "xml_created": xml_result.get("success", False),
                "xml_fcpxml_path": xml_result.get("fcpxml", {}).get("path"),
                "xml_premiere_path": xml_result.get("premiere", {}).get("path"),
                "xml_includes_subtitles": xml_result.get("subtitle_support", False),
                "davinci_script_path": str(davinci_script_path),
                "instructions_path": str(instructions_path),
                "davinci_import": davinci_result
            }
            
        except Exception as e:
            return {"success": False, "message": f"Failed to create editing workflow: {e}"}

    def _convert_to_davinci_format(self, edit_script: EditScript, video_path: str) -> List[Dict[str, Any]]:
        """Convert EditScript to DaVinci Resolve format with frames"""
        davinci_edits = []
        
        # Get the actual frame rate from the video file instead of assuming 30fps
        fps = self._get_video_frame_rate(video_path)
        
        for clip in edit_script.clips:
            # Parse timecode format to seconds
            start_seconds = self._timecode_to_seconds(clip.timecode_in)
            end_seconds = self._timecode_to_seconds(clip.timecode_out)
            
            # Skip clips with invalid timecodes
            if end_seconds <= start_seconds:
                logger.warning(f"Skipping invalid clip: {clip.timecode_in} -> {clip.timecode_out}")
                continue
            
            # Convert to frames
            start_frame = int(start_seconds * fps)
            end_frame = int(end_seconds * fps)
            
            davinci_edit = {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "phrase": clip.phrase,
            }
            davinci_edits.append(davinci_edit)
            
            logger.debug(f"DaVinci clip: {start_seconds:.2f}s-{end_seconds:.2f}s -> frames {start_frame}-{end_frame} @ {fps}fps")
        
        return davinci_edits

    def _get_video_frame_rate(self, video_path: str) -> float:
        """Get the actual frame rate from the video file"""
        try:
            import subprocess
            import json
            
            # Use ffprobe to get the actual frame rate
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json", 
                "-show_streams", video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        r_frame_rate = stream.get("r_frame_rate", "25/1")
                        # Parse fraction like "25/1" or "30000/1001"
                        if "/" in r_frame_rate:
                            num, den = map(int, r_frame_rate.split("/"))
                            fps = num / den
                            logger.info(f"Detected video frame rate: {fps:.2f} fps")
                            return fps
            
            logger.warning(f"Could not determine video frame rate from {video_path}, using 25fps")
            return 25.0
            
        except Exception as e:
            logger.warning(f"Error determining video frame rate: {e}, using 25fps")
            return 25.0
    
    def _create_edl_export(self, edit_script: EditScript, video_path: str, project_dir: Path) -> Dict[str, Any]:
        """Create EDL file for universal editor import"""
        try:
            from .edl_exporter import EDLExporter
            
            # Get video frame rate
            frame_rate = self._get_video_frame_rate(video_path)
            
            # Create EDL exporter
            exporter = EDLExporter(frame_rate=frame_rate)
            
            # Generate EDL path
            edl_path = project_dir / "ai_edit.edl"
            video_filename = Path(video_path).name
            
            # Export EDL
            success = exporter.export_edl(edit_script, video_filename, edl_path)
            
            return {
                "success": success,
                "edl_path": str(edl_path) if success else None,
                "clips_exported": len(edit_script.clips),
                "frame_rate": frame_rate
            }
            
        except Exception as e:
            return {"success": False, "message": f"EDL export failed: {e}"}
    
    def _create_xml_export(self, edit_script: EditScript, video_path: str, project_dir: Path, include_subtitles: bool = False) -> Dict[str, Any]:
        """Create XML files with subtitle support for professional workflows"""
        try:
            from .xml_exporter import XMLExporter
            
            # Get video frame rate
            frame_rate = self._get_video_frame_rate(video_path)
            video_filename = Path(video_path).name
            
            results = {}
            
            # Create Final Cut Pro XML (with subtitles if requested)
            fcpxml_exporter = XMLExporter(frame_rate=frame_rate, format_type="fcpxml")
            fcpxml_path = project_dir / "ai_edit.fcpxml"
            
            # Create subtitle data if requested
            subtitle_data = None
            if include_subtitles:
                subtitle_data = [
                    {
                        "start": clip.timecode_in,
                        "end": clip.timecode_out,
                        "text": clip.phrase
                    }
                    for clip in edit_script.clips
                ]
            
            fcpxml_success = fcpxml_exporter.export_xml(edit_script, video_filename, fcpxml_path, subtitle_data)
            results["fcpxml"] = {
                "success": fcpxml_success,
                "path": str(fcpxml_path) if fcpxml_success else None,
                "includes_subtitles": include_subtitles
            }
            
            # Create Premiere Pro XML (with subtitles if requested)
            premiere_exporter = XMLExporter(frame_rate=frame_rate, format_type="premiere")
            premiere_path = project_dir / "ai_edit_premiere.xml"
            
            premiere_success = premiere_exporter.export_xml(edit_script, video_filename, premiere_path, subtitle_data)
            results["premiere"] = {
                "success": premiere_success,
                "path": str(premiere_path) if premiere_success else None,
                "includes_subtitles": include_subtitles
            }
            
            results["success"] = fcpxml_success or premiere_success
            results["clips_exported"] = len(edit_script.clips)
            results["frame_rate"] = frame_rate
            results["subtitle_support"] = include_subtitles
            
            return results
            
        except Exception as e:
            return {"success": False, "message": f"XML export failed: {e}"}
    
    def _create_import_instructions(self, instructions_path: Path, video_path: str, edl_path: str = None, xml_result: Dict = None):
        """Create comprehensive import instructions for editors"""
        
        video_name = Path(video_path).name
        
        # Build file list dynamically
        files_section = f"""📁 FILES IN THIS PROJECT:
• {video_name} - Source video file
• ai_edit.edl - Edit Decision List (universal)
• final_edit.mp4 - Reference edit created by FFmpeg
• davinci_script.json - DaVinci Resolve script (backup)"""
        
        # Add XML files if they exist
        if xml_result and xml_result.get("success"):
            if xml_result.get("fcpxml", {}).get("success"):
                files_section += "\n• ai_edit.fcpxml - Final Cut Pro XML (with metadata)"
            if xml_result.get("premiere", {}).get("success"):
                files_section += "\n• ai_edit_premiere.xml - Premiere Pro XML (with metadata)"
            
            if xml_result.get("subtitle_support"):
                files_section += "\n✨ XML files include subtitle tracks with AI-generated text!"
        
        # Build workflow options
        workflow_section = """🎯 RECOMMENDED WORKFLOWS:

OPTION 1: EDL IMPORT (UNIVERSAL - WORKS IN ALL EDITORS)
========================================================
1. Open your video editor (DaVinci, Premiere, Final Cut, Avid)
2. Create new project with same frame rate as source video
3. Import the source video: {video_name}
4. Import the EDL file: ai_edit.edl
   • DaVinci: File → Import → Timeline
   • Premiere: File → Import, then drag EDL to timeline
   • Final Cut: File → Import → XML (convert EDL first)
   • Avid: File → Import

✅ RESULT: Perfect edit with audio/video automatically cut and placed""".format(video_name=video_name)
        
        # Add XML workflow if available
        if xml_result and xml_result.get("success"):
            workflow_section += f"""

OPTION 2: XML IMPORT (ADVANCED - WITH SUBTITLE SUPPORT)
========================================================
FOR FINAL CUT PRO:
1. Open Final Cut Pro
2. File → Import → ai_edit.fcpxml
3. All clips, timing, and subtitles imported automatically!

FOR PREMIERE PRO:
1. Open Premiere Pro  
2. File → Import → ai_edit_premiere.xml
3. All clips, timing, and subtitles imported automatically!

FOR DAVINCI RESOLVE:
1. File → Import → Timeline → ai_edit.fcpxml (or .xml)
2. Point to source video when asked: {video_name}

✅ RESULT: Complete edit with audio/video/subtitles perfectly timed!"""
        
        workflow_section += f"""

OPTION 3: MANUAL RECREATION (IF IMPORT FAILS)
==============================================
1. Watch final_edit.mp4 to see the intended edit
2. Use the timecodes in davinci_script.json to manually cut
3. Reference the FFmpeg version for timing verification"""
        
        # Build advantages section
        advantages_section = """🎯 FORMAT ADVANTAGES:

EDL (Edit Decision List):
• Works in ANY professional editor
• Preserves exact timecodes from AI
• Includes both audio and video tracks
• Industry standard format
• Fast, reliable import"""
        
        if xml_result and xml_result.get("success"):
            advantages_section += """

XML (Extended Markup):
• Rich metadata support
• Subtitle tracks included
• Effects and transitions supported  
• Editor-specific optimizations
• Future-proof format"""
            
            if xml_result.get("subtitle_support"):
                advantages_section += """

SUBTITLE FEATURES:
• AI-generated text from edit script
• Perfectly timed to match cuts
• Ready for styling and positioning
• Supports multiple languages
• Professional caption workflow"""
        
        # Combine all sections
        instructions = f"""🎬 AI EDIT IMPORT INSTRUCTIONS
===============================

Generated: {video_name}
Project: YouTube AI Edit

{files_section}

{workflow_section}

{advantages_section}

💡 TIPS:
• If import asks for source video, point to: {video_name}
• Use XML formats for subtitle support
• Use EDL for maximum compatibility
• Reference final_edit.mp4 to verify results"""
        
        with open(instructions_path, 'w') as f:
            f.write(instructions.strip())
        
        logger.info(f"Created comprehensive import instructions: {instructions_path}")

    def _run_davinci_import(self, _davinci_script_path: str, project_dir: str, enhanced_subtitles: bool = False) -> Dict[str, Any]:
        """Run the DaVinci Resolve import script"""
        try:
            # Find the DaVinci importer script
            davinci_importer_path = Path(__file__).parent / "davinci_importer.py"
            
            if not davinci_importer_path.exists():
                return {
                    "success": False,
                    "message": f"DaVinci importer script not found: {davinci_importer_path}",
                }
            
            # Set up DaVinci Resolve environment variables for macOS
            import os
            env = os.environ.copy()
            
            # Set DaVinci Resolve environment variables
            env["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
            env["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
            env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules/"
            
            # Prepare command - use just the filename since we run from project directory
            cmd = [
                "python",
                str(davinci_importer_path),
                "--ai-script-path",
                "davinci_script.json",
            ]
            
            # Add enhanced subtitles flag if enabled
            if enhanced_subtitles:
                cmd.append("--enhanced-subtitles")
                logger.info("Enhanced subtitles mode enabled")
            
            logger.info(f"Running DaVinci import: {' '.join(cmd)}")
            logger.info("DaVinci environment variables configured for macOS")
            
            # Run in project directory so DaVinci script can find the video
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=project_dir, env=env
            )
            
            logger.info(f"DaVinci import process completed with return code: {result.returncode}")
            if result.stdout:
                logger.info(f"DaVinci import stdout: {result.stdout}")
            if result.stderr:
                logger.info(f"DaVinci import stderr: {result.stderr}")
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "DaVinci import completed successfully",
                    "stdout": result.stdout,
                }
            else:
                return {
                    "success": False,
                    "message": f"DaVinci import failed with return code {result.returncode}",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }
                
        except Exception as e:
            return {"success": False, "message": f"Failed to run DaVinci import: {e}"}

    def _timecode_to_seconds(self, timecode: str) -> float:
        """Convert timecode "HH:MM:SS,mmm" or "MM:SS:mmm" to seconds"""
        try:
            # Handle both comma and period as decimal separator
            timecode = timecode.replace(",", ".")
            parts = timecode.split(":")

            if len(parts) == 3:
                # This could be HH:MM:SS.mmm or MM:SS:mmm format
                first_part = int(parts[0])
                second_part = int(parts[1])
                third_part = parts[2]

                # Check if this looks like milliseconds (e.g., "00:04:195" or "04:195")
                if "." not in third_part and len(third_part) == 3:
                    # This is MM:SS:mmm format where third part is milliseconds
                    milliseconds = float(third_part)
                    if first_part < 60:  # Likely MM:SS:mmm format
                        minutes = first_part
                        seconds = second_part + (milliseconds / 1000.0)
                        total_seconds = minutes * 60 + seconds
                        logger.debug(
                            f"Converted timecode {timecode} (MM:SS:mmm) to {total_seconds} seconds"
                        )
                        return total_seconds
                    else:
                        # Treat as HH:MM:SS with milliseconds
                        hours = first_part
                        minutes = second_part
                        seconds = milliseconds / 1000.0
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        logger.debug(
                            f"Converted timecode {timecode} (HH:MM:mmm) to {total_seconds} seconds"
                        )
                        return total_seconds
                else:
                    # Normal HH:MM:SS.mmm format
                    hours = first_part
                    minutes = second_part
                    seconds = float(third_part)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    logger.debug(
                        f"Converted timecode {timecode} (HH:MM:SS.mmm) to {total_seconds} seconds"
                    )
                    return total_seconds

            elif len(parts) == 2:
                # Handle MM:SS format
                minutes = int(parts[0])
                seconds = float(parts[1])
                total_seconds = minutes * 60 + seconds
                logger.debug(
                    f"Converted timecode {timecode} (MM:SS) to {total_seconds} seconds"
                )
                return total_seconds
            else:
                # Try to parse as just seconds
                total_seconds = float(timecode)
                logger.debug(
                    f"Converted timecode {timecode} (seconds) to {total_seconds} seconds"
                )
                return total_seconds
        except ValueError as e:
            logger.warning(
                f"Could not parse timecode: {timecode}, error: {e}, defaulting to 0"
            )
            return 0.0


# Create the graph
youtube_editor_graph = Graph(
    nodes=[GenerateEditScriptNode, DownloadVideoNode, CreateFFmpegEditNode]
)


async def create_youtube_edit(
    youtube_url: str,
    brief: str,
    video_projects_dir: str = "./video_projects",
    cache_edit_scripts: bool = True,
    download_video: bool = True,
    create_final_edit: bool = True,
    enhanced_subtitles: bool = False,
) -> Dict[str, Any]:
    """
    Complete YouTube editing workflow using AI-powered YouTube Director Agent.

    Args:
        youtube_url: YouTube video URL to edit
        brief: Creative brief for the edit
        video_projects_dir: Directory to store project files
        cache_edit_scripts: Whether to cache edit scripts to avoid re-calling Gemini
        download_video: Whether to download the video file
        create_final_edit: Whether to create final edit using FFmpeg
        enhanced_subtitles: Whether to enable enhanced subtitle workflow with transcription

    Returns:
        Dict with workflow results and file paths
    """
    deps = YouTubeEditorDeps(
        video_projects_dir=video_projects_dir,
        cache_edit_scripts=cache_edit_scripts,
        download_video=download_video,
        create_final_edit=create_final_edit,
        enhanced_subtitles=enhanced_subtitles,
    )

    state = YouTubeEditorState(
        youtube_url=youtube_url,
        brief=brief,
    )

    logger.info(f"Starting YouTube Editor workflow for: {youtube_url}")
    logger.info(f"Brief: {brief}")
    logger.info(f"Project UID: {state.project_uid}")

    result = await youtube_editor_graph.run(
        GenerateEditScriptNode(), state=state, deps=deps
    )

    return result.output


__all__ = [
    "youtube_editor_graph",
    "create_youtube_edit",
    "YouTubeEditorState",
    "YouTubeEditorDeps",
]
