"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Media Processor (FFmpeg + Whisper)           ║
╠══════════════════════════════════════════════════════════╣
║  Process video/audio files:                              ║
║    • Transcribe (Whisper API)                            ║
║    • Convert formats (FFmpeg)                            ║
║    • Trim, extract audio, compress                       ║
║    • Get media info                                      ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
import subprocess
import tempfile
from datetime import datetime

logger = logging.getLogger("tars.media")

REPORT_DIR = os.path.expanduser("~/Documents/TARS_Reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def process_media(action, input_path, output_format=None, start=None, end=None,
                  output_path=None, openai_api_key=None):
    """Process a media file.
    
    Args:
        action: transcribe, convert, trim, extract_audio, compress, info
        input_path: Path to input media file
        output_format: For convert (mp3, mp4, wav, etc.)
        start: For trim (HH:MM:SS)
        end: For trim (HH:MM:SS)
        output_path: Custom output path
        openai_api_key: For transcription via Whisper API
    
    Returns:
        Standard tool result dict
    """
    input_path = os.path.expanduser(input_path)

    if not os.path.exists(input_path):
        return {"success": False, "error": True, "content": f"File not found: {input_path}"}

    try:
        if action == "info":
            return _get_info(input_path)
        elif action == "transcribe":
            return _transcribe(input_path, openai_api_key)
        elif action == "convert":
            return _convert(input_path, output_format, output_path)
        elif action == "trim":
            return _trim(input_path, start, end, output_path)
        elif action == "extract_audio":
            return _extract_audio(input_path, output_path)
        elif action == "compress":
            return _compress(input_path, output_path)
        else:
            return {"success": False, "error": True, "content": f"Unknown action: {action}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Media processing error: {e}"}


def _check_ffmpeg():
    """Check if FFmpeg is available."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_info(input_path):
    """Get media file info using FFprobe."""
    if not _check_ffmpeg():
        return {"success": False, "error": True, "content": "FFmpeg not installed. Run: brew install ffmpeg"}

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path],
            capture_output=True, text=True, timeout=30
        )
        info = json.loads(result.stdout)

        fmt = info.get("format", {})
        streams = info.get("streams", [])

        lines = [f"## Media Info: {os.path.basename(input_path)}\n"]
        lines.append(f"Format: {fmt.get('format_long_name', 'unknown')}")
        lines.append(f"Duration: {float(fmt.get('duration', 0)):.1f}s")
        lines.append(f"Size: {int(fmt.get('size', 0)) / 1024 / 1024:.1f} MB")
        lines.append(f"Bitrate: {int(fmt.get('bit_rate', 0)) / 1000:.0f} kbps")

        for s in streams:
            codec_type = s.get("codec_type", "")
            if codec_type == "video":
                lines.append(f"\nVideo: {s.get('codec_name', '?')} {s.get('width', '?')}x{s.get('height', '?')} @ {s.get('r_frame_rate', '?')} fps")
            elif codec_type == "audio":
                lines.append(f"Audio: {s.get('codec_name', '?')} {s.get('sample_rate', '?')} Hz, {s.get('channels', '?')} channels")

        return {"success": True, "content": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": True, "content": f"FFprobe error: {e}"}


def _transcribe(input_path, api_key):
    """Transcribe audio/video to text using Whisper API."""
    if not api_key:
        return {"success": False, "error": True, "content": "OpenAI API key required for transcription. Set voice.openai_api_key or image_generation.api_key in config.yaml."}

    # If video, extract audio first
    ext = os.path.splitext(input_path)[1].lower()
    audio_path = input_path
    cleanup_tmp = False

    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        if not _check_ffmpeg():
            return {"success": False, "error": True, "content": "FFmpeg needed to extract audio from video. Run: brew install ffmpeg"}

        tmp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_audio.close()
        audio_path = tmp_audio.name
        cleanup_tmp = True

        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", audio_path],
            capture_output=True, timeout=120
        )

    try:
        # Whisper API has a 25MB limit — check file size
        file_size = os.path.getsize(audio_path)
        if file_size > 25 * 1024 * 1024:
            return {"success": False, "error": True, "content": f"File too large for Whisper API ({file_size / 1024 / 1024:.1f} MB, max 25 MB). Compress first with process_media(action='compress')."}

        import urllib.request

        boundary = "----TARSMediaBoundary"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="file"; filename="audio.mp3"\r\n'
        body += b"Content-Type: audio/mpeg\r\n\r\n"
        with open(audio_path, "rb") as f:
            body += f.read()
        body += b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += b"whisper-1\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        body += b"verbose_json\r\n"
        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())

        text = result.get("text", "")
        duration = result.get("duration", 0)

        # Save transcript
        transcript_path = os.path.splitext(input_path)[0] + "_transcript.txt"
        with open(transcript_path, "w") as f:
            f.write(text)

        return {
            "success": True,
            "path": transcript_path,
            "content": f"Transcribed {duration:.0f}s of audio. Transcript saved to {transcript_path}\n\n{text[:2000]}"
        }

    finally:
        if cleanup_tmp and os.path.exists(audio_path):
            os.unlink(audio_path)


def _convert(input_path, output_format, output_path):
    """Convert media to a different format."""
    if not _check_ffmpeg():
        return {"success": False, "error": True, "content": "FFmpeg not installed. Run: brew install ffmpeg"}

    if not output_format:
        return {"success": False, "error": True, "content": "output_format required (mp3, mp4, wav, etc.)."}

    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}_converted.{output_format}"

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, output_path],
        capture_output=True, text=True, timeout=300
    )

    if result.returncode != 0:
        return {"success": False, "error": True, "content": f"FFmpeg conversion error: {result.stderr[:300]}"}

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    return {"success": True, "path": output_path, "content": f"Converted to {output_format}: {output_path} ({size_mb:.1f} MB)"}


def _trim(input_path, start, end, output_path):
    """Trim a media file."""
    if not _check_ffmpeg():
        return {"success": False, "error": True, "content": "FFmpeg not installed. Run: brew install ffmpeg"}

    if not start and not end:
        return {"success": False, "error": True, "content": "start and/or end time required for trim."}

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_trimmed{ext}"

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if start:
        cmd.extend(["-ss", start])
    if end:
        cmd.extend(["-to", end])
    cmd.extend(["-c", "copy", output_path])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return {"success": False, "error": True, "content": f"FFmpeg trim error: {result.stderr[:300]}"}

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    return {"success": True, "path": output_path, "content": f"Trimmed clip saved: {output_path} ({size_mb:.1f} MB)"}


def _extract_audio(input_path, output_path):
    """Extract audio track from video."""
    if not _check_ffmpeg():
        return {"success": False, "error": True, "content": "FFmpeg not installed. Run: brew install ffmpeg"}

    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}_audio.mp3"

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path],
        capture_output=True, text=True, timeout=300
    )

    if result.returncode != 0:
        return {"success": False, "error": True, "content": f"FFmpeg extract error: {result.stderr[:300]}"}

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    return {"success": True, "path": output_path, "content": f"Audio extracted: {output_path} ({size_mb:.1f} MB)"}


def _compress(input_path, output_path):
    """Compress a video file."""
    if not _check_ffmpeg():
        return {"success": False, "error": True, "content": "FFmpeg not installed. Run: brew install ffmpeg"}

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed{ext}"

    original_size = os.path.getsize(input_path) / 1024 / 1024

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vcodec", "libx264", "-crf", "28",
         "-preset", "medium", "-acodec", "aac", "-b:a", "128k", output_path],
        capture_output=True, text=True, timeout=600
    )

    if result.returncode != 0:
        return {"success": False, "error": True, "content": f"FFmpeg compress error: {result.stderr[:300]}"}

    new_size = os.path.getsize(output_path) / 1024 / 1024
    reduction = (1 - new_size / original_size) * 100 if original_size > 0 else 0

    return {
        "success": True, "path": output_path,
        "content": f"Compressed: {original_size:.1f} MB → {new_size:.1f} MB ({reduction:.0f}% reduction). Saved to {output_path}"
    }
