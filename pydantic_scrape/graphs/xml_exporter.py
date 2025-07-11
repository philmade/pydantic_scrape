"""
XML Timeline Exporter
Creates Final Cut Pro XML or Premiere Pro XML with full metadata including subtitles
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pydantic_scrape.agents.youtube_director_gemini import EditScript


@dataclass
class XMLClip:
    """Clip data for XML export"""
    id: str
    name: str
    start_frame: int
    end_frame: int
    record_in_frame: int
    record_out_frame: int
    phrase: str
    duration_frames: int


class XMLExporter:
    """Exports AI edit scripts as XML files with subtitle support"""
    
    def __init__(self, frame_rate: float = 25.0, format_type: str = "fcpxml"):
        self.frame_rate = frame_rate
        self.format_type = format_type  # "fcpxml" or "premiere"
        self.framerate_str = f"{int(frame_rate)}s"
    
    def frames_to_timecode(self, frames: int) -> str:
        """Convert frame count to timecode for XML"""
        if self.frame_rate == 0:
            return "0s"
        
        seconds = frames / self.frame_rate
        return f"{seconds:.3f}s"
    
    def timecode_to_frames(self, timecode: str) -> int:
        """Convert timecode to frame count"""
        try:
            # Handle both comma and period as decimal separator
            timecode = timecode.replace(",", ".")
            parts = timecode.split(":")
            
            if len(parts) == 3:
                # Could be HH:MM:SS.mmm or MM:SS:mmm
                first_part = int(parts[0])
                second_part = int(parts[1])
                third_part = parts[2]
                
                if "." not in third_part and len(third_part) == 3:
                    # MM:SS:mmm format
                    if first_part < 60:
                        minutes = first_part
                        seconds = second_part + (float(third_part) / 1000.0)
                        total_seconds = minutes * 60 + seconds
                        return int(total_seconds * self.frame_rate)
                
                # HH:MM:SS.mmm format
                hours = first_part
                minutes = second_part
                seconds = float(third_part)
                total_seconds = hours * 3600 + minutes * 60 + seconds
                return int(total_seconds * self.frame_rate)
            
            elif len(parts) == 2:
                # MM:SS format
                minutes = int(parts[0])
                seconds = float(parts[1])
                total_seconds = minutes * 60 + seconds
                return int(total_seconds * self.frame_rate)
                
        except Exception:
            pass
        
        return 0
    
    def create_fcpxml_from_script(self, edit_script: EditScript, video_filename: str, 
                                  subtitle_data: Optional[List[Dict]] = None) -> ET.Element:
        """Create Final Cut Pro XML from edit script"""
        
        # Root element
        fcpxml = ET.Element("fcpxml", version="1.10")
        
        # Resources section
        resources = ET.SubElement(fcpxml, "resources")
        
        # Format resource
        format_elem = ET.SubElement(resources, "format", {
            "id": "r1",
            "name": f"FFVideoFormat{int(self.frame_rate)}fps",
            "frameDuration": f"1/{int(self.frame_rate)}s",
            "width": "1920",
            "height": "1080"
        })
        
        # Asset resource (source video)
        asset = ET.SubElement(resources, "asset", {
            "id": "r2",
            "name": Path(video_filename).stem,
            "src": video_filename,
            "start": "0s",
            "hasVideo": "1",
            "hasAudio": "1",
            "audioSources": "1",
            "audioChannels": "2"
        })
        
        # Library and event structure
        library = ET.SubElement(fcpxml, "library")
        event = ET.SubElement(library, "event", name="AI Edit Event")
        
        # Project
        project = ET.SubElement(event, "project", name="AI Edit Project")
        sequence = ET.SubElement(project, "sequence", {
            "format": "r1",
            "tcStart": "0s",
            "tcFormat": "NDF",
            "audioLayout": "stereo",
            "audioRate": "48k"
        })
        
        # Spine (main timeline)
        spine = ET.SubElement(sequence, "spine")
        
        # Process clips
        record_timecode = 0
        
        for i, clip in enumerate(edit_script.clips, 1):
            # Convert AI timecodes to frames
            source_in_frames = self.timecode_to_frames(clip.timecode_in)
            source_out_frames = self.timecode_to_frames(clip.timecode_out)
            
            duration_frames = source_out_frames - source_in_frames
            if duration_frames <= 0:
                continue
            
            # Record timecodes
            record_in_frames = record_timecode
            record_out_frames = record_timecode + duration_frames
            
            # Create clip element
            clip_elem = ET.SubElement(spine, "asset-clip", {
                "ref": "r2",
                "name": f"Clip {i:02d}",
                "start": self.frames_to_timecode(source_in_frames),
                "duration": self.frames_to_timecode(duration_frames),
                "offset": self.frames_to_timecode(record_in_frames),
                "tcFormat": "NDF"
            })
            
            # Add video component
            video = ET.SubElement(clip_elem, "video", {
                "ref": "r2",
                "offset": self.frames_to_timecode(record_in_frames),
                "start": self.frames_to_timecode(source_in_frames),
                "duration": self.frames_to_timecode(duration_frames)
            })
            
            # Add audio component
            audio = ET.SubElement(clip_elem, "audio", {
                "ref": "r2", 
                "offset": self.frames_to_timecode(record_in_frames),
                "start": self.frames_to_timecode(source_in_frames),
                "duration": self.frames_to_timecode(duration_frames),
                "role": "dialogue"
            })
            
            # Add subtitle/caption if available
            if subtitle_data:
                self._add_subtitle_to_clip(clip_elem, clip.phrase, record_in_frames, duration_frames)
            
            record_timecode = record_out_frames
        
        # Add subtitle track if we have subtitle data
        if subtitle_data:
            self._add_subtitle_track(spine, edit_script, subtitle_data)
        
        return fcpxml
    
    def _add_subtitle_to_clip(self, clip_elem: ET.Element, text: str, 
                             start_frames: int, duration_frames: int):
        """Add subtitle/caption to a clip element"""
        
        # Create title element for subtitle
        title = ET.SubElement(clip_elem, "title", {
            "ref": "r3",  # Reference to title resource
            "name": "Basic Title",
            "offset": self.frames_to_timecode(start_frames),
            "duration": self.frames_to_timecode(duration_frames)
        })
        
        # Text styling
        text_elem = ET.SubElement(title, "text")
        text_style = ET.SubElement(text_elem, "text-style", {
            "ref": "ts1"
        })
        text_style.text = text[:100]  # Limit subtitle length
    
    def _add_subtitle_track(self, spine: ET.Element, edit_script: EditScript, 
                           subtitle_data: List[Dict]):
        """Add a dedicated subtitle track"""
        
        # Create subtitle spine/track
        subtitle_spine = ET.SubElement(spine, "spine", {
            "name": "Subtitles",
            "lane": "1"
        })
        
        record_timecode = 0
        
        for i, clip in enumerate(edit_script.clips, 1):
            source_in_frames = self.timecode_to_frames(clip.timecode_in)
            source_out_frames = self.timecode_to_frames(clip.timecode_out)
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Create caption element
            caption = ET.SubElement(subtitle_spine, "caption", {
                "name": f"Caption {i:02d}",
                "offset": self.frames_to_timecode(record_timecode),
                "duration": self.frames_to_timecode(duration_frames),
                "role": "captions"
            })
            
            # Caption text
            text_elem = ET.SubElement(caption, "text")
            text_elem.text = clip.phrase
            
            record_timecode += duration_frames
    
    def create_premiere_xml_from_script(self, edit_script: EditScript, video_filename: str,
                                       subtitle_data: Optional[List[Dict]] = None) -> ET.Element:
        """Create Premiere Pro XML from edit script"""
        
        # Root element
        xmeml = ET.Element("xmeml", version="4")
        
        # Project
        project = ET.SubElement(xmeml, "project")
        name_elem = ET.SubElement(project, "name")
        name_elem.text = "AI Edit Project"
        
        # Children (sequences)
        children = ET.SubElement(project, "children")
        
        # Sequence
        sequence = ET.SubElement(children, "sequence")
        seq_name = ET.SubElement(sequence, "name")
        seq_name.text = "AI Edit Sequence"
        
        # Duration
        duration = ET.SubElement(sequence, "duration")
        duration.text = str(sum(self.timecode_to_frames(clip.timecode_out) - 
                               self.timecode_to_frames(clip.timecode_in) 
                               for clip in edit_script.clips))
        
        # Rate
        rate = ET.SubElement(sequence, "rate")
        timebase = ET.SubElement(rate, "timebase")
        timebase.text = str(int(self.frame_rate))
        ntsc = ET.SubElement(rate, "ntsc")
        ntsc.text = "FALSE"
        
        # Media
        media = ET.SubElement(sequence, "media")
        
        # Video track
        video_track = ET.SubElement(media, "video")
        video_track_elem = ET.SubElement(video_track, "track")
        
        # Audio track  
        audio_track = ET.SubElement(media, "audio")
        audio_track_elem = ET.SubElement(audio_track, "track")
        
        record_timecode = 0
        
        for i, clip in enumerate(edit_script.clips, 1):
            source_in_frames = self.timecode_to_frames(clip.timecode_in)
            source_out_frames = self.timecode_to_frames(clip.timecode_out)
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Video clip item
            video_clip = ET.SubElement(video_track_elem, "clipitem", id=f"clipitem-{i}")
            v_name = ET.SubElement(video_clip, "name")
            v_name.text = f"Clip {i:02d}"
            
            v_start = ET.SubElement(video_clip, "start")
            v_start.text = str(record_timecode)
            v_end = ET.SubElement(video_clip, "end") 
            v_end.text = str(record_timecode + duration_frames)
            v_in = ET.SubElement(video_clip, "in")
            v_in.text = str(source_in_frames)
            v_out = ET.SubElement(video_clip, "out")
            v_out.text = str(source_out_frames)
            
            # File reference
            v_file = ET.SubElement(video_clip, "file", id=f"file-{i}")
            v_file_name = ET.SubElement(v_file, "name")
            v_file_name.text = video_filename
            
            # Audio clip item (same structure)
            audio_clip = ET.SubElement(audio_track_elem, "clipitem", id=f"audioclipitem-{i}")
            a_name = ET.SubElement(audio_clip, "name")
            a_name.text = f"Audio {i:02d}"
            
            a_start = ET.SubElement(audio_clip, "start")
            a_start.text = str(record_timecode)
            a_end = ET.SubElement(audio_clip, "end")
            a_end.text = str(record_timecode + duration_frames)
            a_in = ET.SubElement(audio_clip, "in")
            a_in.text = str(source_in_frames)
            a_out = ET.SubElement(audio_clip, "out")
            a_out.text = str(source_out_frames)
            
            # Audio file reference
            a_file = ET.SubElement(audio_clip, "file", id=f"audiofile-{i}")
            a_file_name = ET.SubElement(a_file, "name")
            a_file_name.text = video_filename
            
            record_timecode += duration_frames
        
        # Add subtitle track if available
        if subtitle_data:
            self._add_premiere_subtitle_track(media, edit_script, subtitle_data)
        
        return xmeml
    
    def _add_premiere_subtitle_track(self, media: ET.Element, edit_script: EditScript,
                                    subtitle_data: List[Dict]):
        """Add subtitle track to Premiere XML"""
        
        # Create subtitle track
        subtitle_track = ET.SubElement(media, "video")
        subtitle_track_elem = ET.SubElement(subtitle_track, "track")
        
        record_timecode = 0
        
        for i, clip in enumerate(edit_script.clips, 1):
            source_in_frames = self.timecode_to_frames(clip.timecode_in)
            source_out_frames = self.timecode_to_frames(clip.timecode_out)
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Subtitle clip item
            sub_clip = ET.SubElement(subtitle_track_elem, "generatoritem", id=f"subtitle-{i}")
            sub_name = ET.SubElement(sub_clip, "name")
            sub_name.text = f"Subtitle {i:02d}"
            
            sub_start = ET.SubElement(sub_clip, "start")
            sub_start.text = str(record_timecode)
            sub_end = ET.SubElement(sub_clip, "end")
            sub_end.text = str(record_timecode + duration_frames)
            
            # Effect (subtitle effect)
            effect = ET.SubElement(sub_clip, "effect")
            effect_name = ET.SubElement(effect, "name")
            effect_name.text = "Basic Title"
            
            # Parameters
            parameter = ET.SubElement(effect, "parameter", authoringApp="PremierePro")
            param_name = ET.SubElement(parameter, "name")
            param_name.text = "Text"
            param_value = ET.SubElement(parameter, "value")
            param_value.text = clip.phrase
            
            record_timecode += duration_frames
    
    def export_xml(self, edit_script: EditScript, video_filename: str, output_path: Path,
                   subtitle_data: Optional[List[Dict]] = None) -> bool:
        """Export edit script as XML file"""
        try:
            if self.format_type == "fcpxml":
                xml_root = self.create_fcpxml_from_script(edit_script, video_filename, subtitle_data)
            else:
                xml_root = self.create_premiere_xml_from_script(edit_script, video_filename, subtitle_data)
            
            # Create XML tree and write
            tree = ET.ElementTree(xml_root)
            ET.indent(tree, space="  ", level=0)  # Pretty formatting
            tree.write(output_path, encoding="utf-8", xml_declaration=True)
            
            print(f"✅ {self.format_type.upper()} exported to: {output_path}")
            print(f"📝 {len(edit_script.clips)} clips exported")
            if subtitle_data:
                print(f"📝 Subtitles included in XML")
            print(f"🎬 Ready for import into professional editors")
            
            return True
            
        except Exception as e:
            print(f"❌ XML export failed: {e}")
            return False


def create_xml_from_ai_script(ai_script_path: str, video_path: str, 
                             frame_rate: float = 25.0, xml_format: str = "fcpxml",
                             include_subtitles: bool = True) -> str:
    """
    Create XML file from AI script JSON with subtitle support
    
    Args:
        ai_script_path: Path to the AI script JSON file
        video_path: Path to the source video file  
        frame_rate: Video frame rate (default 25fps)
        xml_format: "fcpxml" or "premiere"
        include_subtitles: Whether to include subtitle tracks
    
    Returns:
        Path to created XML file
    """
    
    # Load AI script
    with open(ai_script_path, 'r') as f:
        script_data = json.load(f)
    
    edit_script = EditScript.model_validate({"clips": script_data})
    
    # Create subtitle data from phrases
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
    
    # Create XML exporter
    exporter = XMLExporter(frame_rate=frame_rate, format_type=xml_format)
    
    # Generate output path
    script_path = Path(ai_script_path)
    xml_ext = ".fcpxml" if xml_format == "fcpxml" else ".xml"
    xml_path = script_path.parent / f"{script_path.stem}{xml_ext}"
    
    # Export XML
    video_filename = Path(video_path).name
    success = exporter.export_xml(edit_script, video_filename, xml_path, subtitle_data)
    
    if success:
        return str(xml_path)
    else:
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python xml_exporter.py <ai_script.json> <video_file> [frame_rate] [format] [subtitles]")
        print("  format: fcpxml or premiere (default: fcpxml)")
        print("  subtitles: true or false (default: true)")
        sys.exit(1)
    
    ai_script_path = sys.argv[1]
    video_path = sys.argv[2]
    frame_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
    xml_format = sys.argv[4] if len(sys.argv) > 4 else "fcpxml"
    include_subtitles = sys.argv[5].lower() != "false" if len(sys.argv) > 5 else True
    
    xml_path = create_xml_from_ai_script(ai_script_path, video_path, frame_rate, xml_format, include_subtitles)
    
    if xml_path:
        print(f"\n🎯 SUCCESS!")
        print(f"📁 XML file: {xml_path}")
        print(f"🎬 Import this XML into your editor:")
        if xml_format == "fcpxml":
            print(f"   • Final Cut Pro: File → Import → {Path(xml_path).name}")
            print(f"   • DaVinci Resolve: File → Import → Timeline")
        else:
            print(f"   • Premiere Pro: File → Import → {Path(xml_path).name}")
            print(f"   • DaVinci Resolve: File → Import → Timeline")
        
        if include_subtitles:
            print(f"✨ INCLUDES SUBTITLES:")
            print(f"   • Subtitle track with AI-generated text")
            print(f"   • Perfectly timed to match edit points")
            print(f"   • Ready for styling and positioning")
            
    else:
        print("❌ XML creation failed")
        sys.exit(1)