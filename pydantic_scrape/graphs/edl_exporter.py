"""
EDL (Edit Decision List) Exporter
Creates industry-standard EDL files from AI edit scripts for import into any video editor
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
from pydantic_scrape.agents.youtube_director_gemini import EditScript


@dataclass
class EDLEvent:
    """Single event in an EDL"""
    event_number: int
    reel_name: str
    track: str
    transition: str
    source_in: str
    source_out: str
    record_in: str
    record_out: str
    clip_name: str = ""


class EDLExporter:
    """Exports AI edit scripts as EDL files for professional video editors"""
    
    def __init__(self, frame_rate: float = 25.0):
        self.frame_rate = frame_rate
    
    def frames_to_timecode(self, frames: int) -> str:
        """Convert frame count to timecode HH:MM:SS:FF"""
        if self.frame_rate == 0:
            return "00:00:00:00"
        
        ff = int(frames % self.frame_rate)
        ss = int((frames / self.frame_rate) % 60)
        mm = int((frames / (self.frame_rate * 60)) % 60)
        hh = int(frames / (self.frame_rate * 3600))
        
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"
    
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
    
    def create_edl_from_script(self, edit_script: EditScript, video_filename: str) -> str:
        """Create EDL content from edit script"""
        
        # EDL Header
        edl_content = [
            "TITLE: AI Edit",
            "FCM: NON-DROP FRAME",
            "",
        ]
        
        record_timecode = 0  # Running record timecode
        
        for i, clip in enumerate(edit_script.clips, 1):
            # Convert AI timecodes to frames
            source_in_frames = self.timecode_to_frames(clip.timecode_in)
            source_out_frames = self.timecode_to_frames(clip.timecode_out)
            
            # Calculate duration
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Record timecodes
            record_in_frames = record_timecode
            record_out_frames = record_timecode + duration_frames
            
            # Create EDL event
            event = EDLEvent(
                event_number=i,
                reel_name="001",  # Single source reel
                track="V",  # Video track
                transition="C",  # Cut transition
                source_in=self.frames_to_timecode(source_in_frames),
                source_out=self.frames_to_timecode(source_out_frames),
                record_in=self.frames_to_timecode(record_in_frames),
                record_out=self.frames_to_timecode(record_out_frames),
                clip_name=clip.phrase[:32]  # Clip name (limited length)
            )
            
            # Format EDL line
            edl_line = f"{event.event_number:03d}  {event.reel_name}       {event.track}     {event.transition}        {event.source_in} {event.source_out} {event.record_in} {event.record_out}"
            edl_content.append(edl_line)
            
            # Add clip name as comment
            if event.clip_name:
                edl_content.append(f"* FROM CLIP NAME: {event.clip_name}")
            
            # Add audio track
            audio_event = EDLEvent(
                event_number=i,
                reel_name="001",
                track="A",  # Audio track
                transition="C",
                source_in=self.frames_to_timecode(source_in_frames),
                source_out=self.frames_to_timecode(source_out_frames),
                record_in=self.frames_to_timecode(record_in_frames),
                record_out=self.frames_to_timecode(record_out_frames)
            )
            
            audio_line = f"{audio_event.event_number:03d}  {audio_event.reel_name}       {audio_event.track}     {audio_event.transition}        {audio_event.source_in} {audio_event.source_out} {audio_event.record_in} {audio_event.record_out}"
            edl_content.append(audio_line)
            
            # Update record timecode for next clip
            record_timecode = record_out_frames
        
        return "\n".join(edl_content)
    
    def export_edl(self, edit_script: EditScript, video_filename: str, output_path: Path) -> bool:
        """Export edit script as EDL file"""
        try:
            edl_content = self.create_edl_from_script(edit_script, video_filename)
            
            with open(output_path, 'w') as f:
                f.write(edl_content)
            
            print(f"✅ EDL exported to: {output_path}")
            print(f"📝 {len(edit_script.clips)} clips exported")
            print(f"🎬 Ready for import into any video editor")
            
            return True
            
        except Exception as e:
            print(f"❌ EDL export failed: {e}")
            return False


def create_edl_from_ai_script(ai_script_path: str, video_path: str, frame_rate: float = 25.0) -> str:
    """
    Create EDL file from AI script JSON
    
    Args:
        ai_script_path: Path to the AI script JSON file
        video_path: Path to the source video file
        frame_rate: Video frame rate (default 25fps)
    
    Returns:
        Path to created EDL file
    """
    
    # Load AI script
    with open(ai_script_path, 'r') as f:
        script_data = json.load(f)
    
    edit_script = EditScript.model_validate({"clips": script_data})
    
    # Create EDL exporter
    exporter = EDLExporter(frame_rate=frame_rate)
    
    # Generate output path
    script_path = Path(ai_script_path)
    edl_path = script_path.parent / f"{script_path.stem}.edl"
    
    # Export EDL
    video_filename = Path(video_path).name
    success = exporter.export_edl(edit_script, video_filename, edl_path)
    
    if success:
        return str(edl_path)
    else:
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python edl_exporter.py <ai_script.json> <video_file> [frame_rate]")
        sys.exit(1)
    
    ai_script_path = sys.argv[1]
    video_path = sys.argv[2]
    frame_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
    
    edl_path = create_edl_from_ai_script(ai_script_path, video_path, frame_rate)
    
    if edl_path:
        print(f"\n🎯 SUCCESS!")
        print(f"📁 EDL file: {edl_path}")
        print(f"🎬 Import this EDL into any video editor:")
        print(f"   • DaVinci Resolve: File → Import → Timeline")
        print(f"   • Premiere Pro: File → Import")
        print(f"   • Final Cut Pro: File → Import → XML")
        print(f"   • Avid: File → Import")
    else:
        print("❌ EDL creation failed")
        sys.exit(1)