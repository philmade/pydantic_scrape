
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger
from openai import OpenAI
from dataclasses import dataclass

@dataclass
class WordTimestamp:
    """Individual word with precise timestamp from Whisper"""
    word: str
    start: float  # seconds
    end: float    # seconds

@dataclass
class TranscriptionResult:
    """Complete result from video transcription with word-level timestamps"""
    source_path: str
    audio_format: str
    audio_size_mb: float
    duration_seconds: float
    frame_rate: float
    full_text: str
    language: str
    word_timestamps: List[WordTimestamp]
    whisper_model: str = "whisper-1"
    processing_time_seconds: float = 0.0
    word_count: int = 0
    json_path: str = ""
    text_path: str = ""
    srt_path: str = ""

    def __post_init__(self):
        if self.word_timestamps:
            self.word_count = len(self.word_timestamps)

class TranscriptionService:
    """A service for transcribing video files."""

    def __init__(self, audio_bitrate: str = "32k", audio_sample_rate: int = 16000, cleanup_audio: bool = True):
        self.audio_bitrate = audio_bitrate
        self.audio_sample_rate = audio_sample_rate
        self.cleanup_audio = cleanup_audio
        self.client = OpenAI()

    def _extract_audio(self, video_path: Path, audio_path: Path) -> bool:
        """Extract compressed audio from video file"""
        try:
            cmd = [
                'ffmpeg', '-i', str(video_path),
                '-acodec', 'mp3',
                '-ab', self.audio_bitrate,
                '-ar', str(self.audio_sample_rate),
                '-ac', '1',  # mono
                '-y',  # overwrite
                str(audio_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return False

    def _get_frame_rate(self, video_path: Path) -> float:
        """Get video frame rate using ffprobe."""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=r_frame_rate',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # The output is a fraction like '30000/1001', evaluate it to get the float.
            num, den = map(int, result.stdout.strip().split('/'))
            return num / den
        except (subprocess.CalledProcessError, ValueError, ZeroDivisionError) as e:
            logger.warning(f"Could not determine frame rate using ffprobe ({e}). Falling back to 30.0 fps.")
            return 30.0

    def _transcribe_audio(self, audio_path: Path) -> Dict[str, Any]:
        """Transcribe audio using Whisper API"""
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                    language="en"
                )
            return transcript.model_dump()
        except Exception as e:
            logger.error(f"Whisper API failed: {e}")
            raise

    def transcribe_video(self, file_path: str) -> TranscriptionResult:
        """
        Main method to transcribe a video or audio file with word-level timestamps.
        Checks for existing transcript before transcribing.
        If a video file is provided, audio is extracted first.
        If an audio file is provided, it's used directly.
        """
        import time
        start_time = time.time()
        input_path = Path(file_path)
        output_dir = input_path.parent
        transcript_json_path = output_dir / "transcript.json"

        # Check for existing transcript
        if transcript_json_path.exists():
            logger.info(f"Found existing transcript: {transcript_json_path}. Loading from cache.")
            try:
                with open(transcript_json_path, 'r', encoding='utf-8') as f:
                    transcript_data = json.load(f)
                
                if 'frame_rate' not in transcript_data or not transcript_data['frame_rate']:
                    logger.info("Older transcript format found. Getting frame rate...")
                    # We need the original video file to get the frame rate, which we might not have here.
                    # For now, we'll have to rely on it being present.
                    # A better solution would be to pass the video path in separately if needed.
                    transcript_data['frame_rate'] = self._get_frame_rate(input_path)
                    with open(transcript_json_path, 'w', encoding='utf-8') as f_out:
                        json.dump(transcript_data, f_out, indent=2, default=lambda o: o.__dict__)
                    logger.info("Updated transcript file with frame rate.")

                if 'word_timestamps' in transcript_data and transcript_data['word_timestamps'] is not None:
                    transcript_data['word_timestamps'] = [WordTimestamp(**w) for w in transcript_data['word_timestamps']]
                transcript_data['full_text'] = transcript_data.get('full_text', '')
                transcript_data['language'] = transcript_data.get('language', '')
                transcript_data['json_path'] = str(transcript_json_path)
                transcript_data['text_path'] = str(output_dir / "transcript.txt")
                transcript_data['srt_path'] = str(output_dir / "transcript.srt")
                return TranscriptionResult(**transcript_data)
            except Exception as e:
                logger.warning(f"Failed to load existing transcript ({e}). Re-transcribing.")

        # Determine if the input is video or audio
        is_audio = input_path.suffix.lower() in ['.mp3', '.wav', '.m4a', '.aac']
        
        if is_audio:
            audio_path = input_path
            logger.info(f"Input is an audio file: {audio_path}. Skipping extraction.")
        else:
            logger.info(f"Input is a video file: {input_path}. Extracting audio.")
            audio_path = output_dir / f"{input_path.stem}_audio.mp3"
            if not self._extract_audio(input_path, audio_path):
                raise RuntimeError("Failed to extract audio from video")

        try:
            audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
            # If it was a video, we get the frame rate. If audio, we can default to 0 or a standard.
            frame_rate = self._get_frame_rate(input_path) if not is_audio else 0.0
            
            transcript_data = self._transcribe_audio(audio_path)

            word_timestamps = [WordTimestamp(word=w['word'], start=w['start'], end=w['end']) for w in transcript_data.get('words', [])]
            duration = transcript_data.get('duration', 0)
            processing_time = time.time() - start_time

            result = TranscriptionResult(
                source_path=str(input_path),
                audio_format=input_path.suffix,
                audio_size_mb=audio_size_mb,
                duration_seconds=duration,
                frame_rate=frame_rate,
                full_text=transcript_data.get('text', ''),
                language=transcript_data.get('language', ''),
                word_timestamps=word_timestamps,
                processing_time_seconds=processing_time,
            )

            self._save_transcript_files(result, output_dir)
            return result
        finally:
            # Only clean up the audio if it was an intermediate file we created
            if not is_audio and self.cleanup_audio and audio_path.exists():
                logger.info(f"Cleaning up temporary audio file: {audio_path}")
                audio_path.unlink()

    def _save_transcript_files(self, transcript_result: TranscriptionResult, output_dir: Path):
        """Save transcript in multiple formats."""
        base_path = output_dir / "transcript"
        transcript_result.json_path = str(base_path.with_suffix('.json'))
        transcript_result.text_path = str(base_path.with_suffix('.txt'))
        transcript_result.srt_path = str(base_path.with_suffix('.srt'))

        with open(transcript_result.json_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(transcript_result.__dict__, f, indent=2, default=lambda o: o.__dict__)

        with open(transcript_result.text_path, 'w', encoding='utf-8') as f:
            f.write(transcript_result.full_text)

        self._create_srt(transcript_result, transcript_result.srt_path)

    def _create_srt(self, transcript: TranscriptionResult, srt_path: str):
        """Create SRT file from word timestamps"""
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, word in enumerate(transcript.word_timestamps):
                f.write(f"{i+1}\n")
                f.write(f"{self._format_srt_timestamp(word.start)} --> {self._format_srt_timestamp(word.end)}\n")
                f.write(f"{word.word}\n\n")

    def _format_srt_timestamp(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
