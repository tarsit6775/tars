"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Voice Interface (STT + TTS)                  ║
╠══════════════════════════════════════════════════════════╣
║  Full conversational voice mode:                         ║
║    • Microphone input → Speech-to-Text (Whisper API)     ║
║    • TTS output → macOS `say` or OpenAI TTS              ║
║    • Voice Activity Detection (energy-based)             ║
║    • Runs as parallel input channel alongside iMessage   ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import io
import time
import wave
import struct
import logging
import threading
import subprocess
import tempfile
from datetime import datetime

logger = logging.getLogger("TARS")

# Audio config
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.1  # 100ms chunks
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)

# Voice activity detection
SILENCE_THRESHOLD = 500      # RMS energy threshold (adjust per mic)
SILENCE_DURATION = 1.5        # Seconds of silence to end utterance
MIN_SPEECH_DURATION = 0.3     # Minimum speech duration to process (ignore clicks)
MAX_SPEECH_DURATION = 60.0    # Max seconds for a single utterance


class VoiceInterface:
    """Full-duplex voice interface for TARS.
    
    Listens on the default microphone, transcribes with Whisper,
    and speaks responses via macOS `say` or OpenAI TTS.
    
    Usage:
        voice = VoiceInterface(config, on_message=callback)
        voice.start()   # starts listening in background thread
        voice.speak("Hello, I'm TARS.")
        voice.stop()
    """

    def __init__(self, config, on_message=None):
        """
        Args:
            config: TARS config dict (needs voice section + openai API key)
            on_message: Callback(text: str, source: str) called when user speaks.
                        Same signature as iMessage ingestion.
        """
        self.config = config
        self._on_message = on_message
        self._running = False
        self._listening = True  # Can be paused during TTS playback
        self._listen_thread = None
        self._speak_lock = threading.Lock()  # Prevent overlapping TTS

        # Voice config
        voice_cfg = config.get("voice", {})
        self.enabled = voice_cfg.get("enabled", False)
        self.tts_engine = voice_cfg.get("tts_engine", "macos")       # "macos" or "openai"
        self.stt_engine = voice_cfg.get("stt_engine", "whisper_api") # "whisper_api" or "whisper_local"
        self.tts_voice = voice_cfg.get("tts_voice", "Daniel")        # macOS voice name
        self.tts_rate = voice_cfg.get("tts_rate", 190)               # Words per minute
        self.silence_threshold = voice_cfg.get("silence_threshold", SILENCE_THRESHOLD)
        self.wake_word = voice_cfg.get("wake_word", "")              # Optional, empty = always listen

        # OpenAI key for Whisper API
        self._openai_key = voice_cfg.get("openai_api_key", "") or config.get("openai", {}).get("api_key", "")

        # State
        self._is_speaking = False
        self._last_speech_time = 0

    # ─── Public API ──────────────────────────────────

    def start(self):
        """Start the voice listener in a background thread."""
        if not self.enabled:
            logger.info("  🎤 Voice interface disabled (set voice.enabled: true in config)")
            return False

        # Check dependencies
        if not self._check_dependencies():
            return False

        self._running = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True, name="tars-voice")
        self._listen_thread.start()
        logger.info(f"  🎤 Voice interface active (STT: {self.stt_engine}, TTS: {self.tts_engine})")
        return True

    def stop(self):
        """Stop the voice listener."""
        self._running = False
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=3)
        logger.info("  🎤 Voice interface stopped")

    def speak(self, text):
        """Speak text via TTS. Thread-safe, blocks until done."""
        if not text or not text.strip():
            return

        with self._speak_lock:
            self._is_speaking = True
            self._listening = False  # Pause mic to avoid feedback

            try:
                # Clean text for speech (remove emoji, markdown)
                clean = self._clean_for_speech(text)
                if not clean:
                    return

                if self.tts_engine == "openai":
                    self._speak_openai(clean)
                else:
                    self._speak_macos(clean)
            except Exception as e:
                logger.warning(f"  🔊 TTS error: {e}")
            finally:
                self._is_speaking = False
                time.sleep(0.3)  # Brief pause before re-enabling mic
                self._listening = True

    @property
    def is_active(self):
        return self._running and self.enabled

    # ─── Listening Loop ──────────────────────────────

    def _listen_loop(self):
        """Main listening loop — captures audio, detects speech, transcribes."""
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            logger.error("  ❌ Voice requires: pip install sounddevice numpy")
            self._running = False
            return

        logger.info("  🎤 Listening on default microphone...")

        audio_buffer = []
        speech_started = False
        silence_start = None
        speech_start_time = None

        def audio_callback(indata, frames, time_info, status):
            """Called by sounddevice for each audio chunk."""
            if status:
                logger.debug(f"  🎤 Audio status: {status}")

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
            ) as stream:
                while self._running:
                    if not self._listening or self._is_speaking:
                        time.sleep(0.1)
                        continue

                    # Read audio chunk
                    try:
                        data, overflowed = stream.read(CHUNK_SIZE)
                        if overflowed:
                            logger.debug("  🎤 Audio buffer overflow")
                    except Exception:
                        time.sleep(0.1)
                        continue

                    # Calculate RMS energy
                    import numpy as np
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))

                    if rms > self.silence_threshold:
                        # Speech detected
                        if not speech_started:
                            speech_started = True
                            speech_start_time = time.time()
                            audio_buffer = []
                            logger.debug("  🎤 Speech detected...")

                        audio_buffer.append(data.copy())
                        silence_start = None

                        # Check max duration
                        elapsed = time.time() - speech_start_time
                        if elapsed > MAX_SPEECH_DURATION:
                            logger.debug("  🎤 Max duration reached, processing...")
                            self._process_audio(audio_buffer)
                            audio_buffer = []
                            speech_started = False

                    elif speech_started:
                        # Silence during speech — might be end of utterance
                        audio_buffer.append(data.copy())

                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > SILENCE_DURATION:
                            # Enough silence — utterance complete
                            speech_duration = time.time() - speech_start_time - SILENCE_DURATION
                            if speech_duration >= MIN_SPEECH_DURATION:
                                logger.debug(f"  🎤 Utterance complete ({speech_duration:.1f}s)")
                                self._process_audio(audio_buffer)
                            else:
                                logger.debug("  🎤 Too short, ignoring")
                            audio_buffer = []
                            speech_started = False
                            silence_start = None

        except Exception as e:
            logger.error(f"  ❌ Voice listener error: {e}")
            self._running = False

    def _process_audio(self, audio_buffer):
        """Convert audio buffer to WAV and send to STT."""
        if not audio_buffer:
            return

        try:
            import numpy as np

            # Concatenate audio chunks
            audio_data = np.concatenate(audio_buffer)

            # Convert to WAV bytes
            wav_bytes = self._to_wav_bytes(audio_data)

            # Transcribe
            text = self._transcribe(wav_bytes)

            if text and text.strip():
                # Check wake word if configured
                if self.wake_word:
                    text_lower = text.lower().strip()
                    wake_lower = self.wake_word.lower()
                    if not text_lower.startswith(wake_lower):
                        logger.debug(f"  🎤 No wake word, ignoring: {text[:50]}")
                        return
                    # Strip wake word from the text
                    text = text[len(self.wake_word):].strip()
                    if not text:
                        # Just the wake word, nothing else
                        self.speak("Yeah?")
                        return

                logger.info(f"  🎤 Heard: {text}")
                self._last_speech_time = time.time()

                # Deliver to TARS via callback
                if self._on_message:
                    self._on_message(text, "voice")

        except Exception as e:
            logger.error(f"  🎤 Audio processing error: {e}")

    # ─── Speech-to-Text ──────────────────────────────

    def _transcribe(self, wav_bytes):
        """Transcribe WAV audio to text using Whisper."""
        if self.stt_engine == "whisper_local":
            return self._transcribe_local(wav_bytes)
        else:
            return self._transcribe_api(wav_bytes)

    def _transcribe_api(self, wav_bytes):
        """Transcribe using OpenAI Whisper API."""
        if not self._openai_key:
            logger.error("  ❌ Whisper API needs openai_api_key in voice config")
            return None

        try:
            import urllib.request
            import json

            # Build multipart form data
            boundary = "----TARSVoiceBoundary"
            body = b""
            # File field
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            body += b"Content-Type: audio/wav\r\n\r\n"
            body += wav_bytes
            body += b"\r\n"
            # Model field
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
            body += b"whisper-1\r\n"
            # Language field (optional, speeds up recognition)
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
            body += b"en\r\n"
            body += f"--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/transcriptions",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._openai_key}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result.get("text", "").strip()

        except Exception as e:
            logger.error(f"  🎤 Whisper API error: {e}")
            return None

    def _transcribe_local(self, wav_bytes):
        """Transcribe using local Whisper model (requires openai-whisper package)."""
        try:
            import whisper

            # Write to temp file (whisper needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            try:
                # Load model (cached after first call)
                if not hasattr(self, '_whisper_model'):
                    logger.info("  🎤 Loading local Whisper model (first time)...")
                    self._whisper_model = whisper.load_model("base")

                result = self._whisper_model.transcribe(tmp_path, language="en")
                return result.get("text", "").strip()
            finally:
                os.unlink(tmp_path)

        except ImportError:
            logger.error("  ❌ Local Whisper needs: pip install openai-whisper")
            return None
        except Exception as e:
            logger.error(f"  🎤 Local Whisper error: {e}")
            return None

    # ─── Text-to-Speech ──────────────────────────────

    def _speak_macos(self, text):
        """Speak using macOS `say` command."""
        try:
            cmd = ["say", "-v", self.tts_voice, "-r", str(self.tts_rate), text]
            subprocess.run(cmd, timeout=120, capture_output=True)
        except subprocess.TimeoutExpired:
            logger.warning("  🔊 TTS timed out (>120s)")
        except Exception as e:
            logger.warning(f"  🔊 macOS TTS error: {e}")

    def _speak_openai(self, text):
        """Speak using OpenAI TTS API."""
        if not self._openai_key:
            logger.warning("  🔊 OpenAI TTS needs api key, falling back to macOS")
            return self._speak_macos(text)

        try:
            import urllib.request
            import json

            payload = json.dumps({
                "model": "tts-1",
                "input": text[:4096],  # API limit
                "voice": "onyx",      # Deep, authoritative — fits TARS
                "response_format": "mp3",
            }).encode()

            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/speech",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._openai_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_data = resp.read()

            # Play via afplay (macOS)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_data)
                tmp_path = f.name

            try:
                subprocess.run(["afplay", tmp_path], timeout=120, capture_output=True)
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.warning(f"  🔊 OpenAI TTS error: {e}, falling back to macOS")
            self._speak_macos(text)

    # ─── Utilities ───────────────────────────────────

    def _to_wav_bytes(self, audio_data):
        """Convert numpy int16 array to WAV bytes."""
        import numpy as np
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

    @staticmethod
    def _clean_for_speech(text):
        """Clean text for natural TTS output."""
        import re
        # Remove emoji (Unicode emoji ranges)
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
                      r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
                      r'\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
                      r'\U0001F900-\U0001F9FF\U00002600-\U000026FF'
                      r'\U00002700-\U000027BF✅❌⚠️🔧💡📋🎯⚡🔍📨]+', '', text)
        # Remove markdown formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
        text = re.sub(r'`(.+?)`', r'\1', text)        # `code`
        text = re.sub(r'#{1,6}\s', '', text)           # ### headers
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text) # [links](url)
        # Remove multiple spaces/newlines
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _check_dependencies(self):
        """Check if required packages are installed."""
        missing = []
        try:
            import sounddevice
        except ImportError:
            missing.append("sounddevice")
        try:
            import numpy
        except ImportError:
            missing.append("numpy")

        if missing:
            logger.error(f"  ❌ Voice interface needs: pip install {' '.join(missing)}")
            return False

        # Check mic access
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_input = sd.query_devices(kind='input')
            logger.info(f"  🎤 Mic: {default_input['name']}")
        except Exception as e:
            logger.error(f"  ❌ No microphone found: {e}")
            return False

        return True
