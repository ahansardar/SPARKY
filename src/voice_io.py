import os
import platform
import subprocess
import tempfile
import threading
import wave
import audioop
from pathlib import Path
import re
import time

import pyaudio

class PiperTTS:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.piper_exe = project_root / "piper" / "piper.exe"
        self.voice_model = project_root / "models" / "en_US-lessac-medium.onnx"
        self._speak_lock = threading.Lock()

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        if not self.piper_exe.exists():
            raise RuntimeError(f"Piper binary not found: {self.piper_exe}")
        if not self.voice_model.exists():
            raise RuntimeError(f"Piper model not found: {self.voice_model}")

        with self._speak_lock:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                out_wav = Path(tf.name)

            try:
                proc = subprocess.run(
                    [
                        str(self.piper_exe),
                        "--model",
                        str(self.voice_model),
                        "--output_file",
                        str(out_wav),
                    ],
                    input=text,
                    text=True,
                    capture_output=True,
                    cwd=str(self.project_root),
                    timeout=60,
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or "piper failed")
                self._play_wav(out_wav)
            finally:
                try:
                    os.unlink(out_wav)
                except Exception:
                    pass

    def _play_wav(self, wav_path: Path) -> None:
        if platform.system() == "Windows":
            import winsound

            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
            return

        wf = wave.open(str(wav_path), "rb")
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pa.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )
        try:
            data = wf.readframes(1024)
            while data:
                stream.write(data)
                data = wf.readframes(1024)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            wf.close()


class VoiceIO:
    def __init__(self, project_root: Path, stt_cache_dir: Path | None = None):
        self.project_root = project_root
        self.tts = PiperTTS(project_root=project_root)
        self._wake_recognizer = None
        self._wake_speechrec_ok = None
        self._oww_model = None
        self._oww_model_loaded_for: str | None = None
        self._oww_ok: bool | None = None
        self._oww_threshold = float(os.getenv("SPARKY_WAKEWORD_THRESHOLD", "0.30"))
        self._oww_any_threshold = float(os.getenv("SPARKY_OWW_ANY_THRESHOLD", "0.55"))
        self._wake_rms_threshold = int(os.getenv("SPARKY_WAKE_RMS_THRESHOLD", "80"))
        self._oww_builtin_model = os.getenv("SPARKY_OWW_MODEL", "hey_sparky").strip().lower()
        self._wake_cue_path = self.project_root / "assets" / "wake.wav"
        self._sleep_cue_path = self.project_root / "assets" / "sleep.wav"

    def _ensure_wake_recognizer(self):
        if self._wake_speechrec_ok is False:
            return None
        if self._wake_recognizer is not None:
            return self._wake_recognizer
        try:
            import speech_recognition as sr
            self._wake_recognizer = sr.Recognizer()
            self._wake_speechrec_ok = True
            return self._wake_recognizer
        except Exception:
            self._wake_speechrec_ok = False
            return None

    def _find_custom_wake_model(self, wakeword: str) -> Path | None:
        models_dir = self.project_root / "models"
        if not models_dir.exists():
            return None
        name = wakeword.lower().strip()
        candidates = list(models_dir.glob(f"{name}*.onnx")) + list(models_dir.glob(f"{name}*.tflite"))
        if not candidates:
            return None
        return candidates[0]

    def _ensure_openwakeword(self, wakeword: str):
        if self._oww_ok is False:
            return None
        if self._oww_model is not None and self._oww_model_loaded_for == wakeword.lower().strip():
            return self._oww_model
        try:
            from openwakeword.model import Model  # type: ignore
            from openwakeword import utils as oww_utils  # type: ignore

            custom_model = self._find_custom_wake_model(wakeword)
            if custom_model is not None:
                self._oww_model = Model(
                    wakeword_models=[str(custom_model)],
                    inference_framework="onnx",
                )
            else:
                try:
                    self._oww_model = Model(
                        wakeword_models=[self._oww_builtin_model],
                        inference_framework="onnx",
                    )
                except Exception:
                    oww_utils.download_models([self._oww_builtin_model])
                    self._oww_model = Model(
                        wakeword_models=[self._oww_builtin_model],
                        inference_framework="onnx",
                    )
            self._oww_model_loaded_for = wakeword.lower().strip()
            self._oww_ok = True
            return self._oww_model
        except Exception:
            self._oww_ok = False
            return None

    def _detect_with_openwakeword(self, pcm: bytes, wakeword: str) -> bool:
        model = self._ensure_openwakeword(wakeword)
        if model is None:
            return False
        try:
            import numpy as np

            target = wakeword.lower().strip()
            audio = np.frombuffer(pcm, dtype=np.int16)
            chunk_size = 1280
            peak_target = 0.0
            peak_any = 0.0

            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                if len(chunk) == 0:
                    continue
                if len(chunk) < chunk_size:
                    padded = np.zeros(chunk_size, dtype=np.int16)
                    padded[:len(chunk)] = chunk
                    chunk = padded

                scores = model.predict(chunk)
                if not isinstance(scores, dict):
                    continue

                for key, raw_score in scores.items():
                    try:
                        score = float(raw_score)
                    except Exception:
                        continue
                    if score > peak_any:
                        peak_any = score
                    k = str(key).lower()
                    if target in k:
                        if score > peak_target:
                            peak_target = score

            if peak_target >= self._oww_threshold:
                return True
            # If no custom Sparky model is present, allow strongest built-in detector
            # as a backup trigger threshold.
            if self._find_custom_wake_model(wakeword) is None and peak_any >= max(self._oww_any_threshold, self._oww_threshold):
                return True
            return False
        except Exception:
            return False

    def transcribe_once(self, seconds: int = 6, level_callback=None) -> str:
        seconds = max(1, min(int(seconds), 6))
        sample_rate = 16000
        frames_per_buffer = 1024
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=frames_per_buffer,
        )
        frames = []
        try:
            for _ in range(int(sample_rate / frames_per_buffer * seconds)):
                chunk = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(chunk)
                if level_callback is not None:
                    try:
                        rms = audioop.rms(chunk, 2) / 32768.0
                        level_callback(max(0.0, min(1.0, rms * 4.0)))
                    except Exception:
                        pass
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        pcm = b"".join(frames)
        if not pcm:
            return ""

        try:
            import speech_recognition as sr

            rec = sr.Recognizer()
            audio = sr.AudioData(pcm, sample_rate, 2)
            text = rec.recognize_google(audio, language="en-US")
            return (text or "").strip()
        except Exception:
            return ""

    def detect_wakeword_once(self, wakeword: str = "hey_sparky", seconds: int = 1) -> bool:
        sample_rate = 16000
        frames_per_buffer = 1024
        pa = pyaudio.PyAudio()
        open_kwargs = {
            "format": pyaudio.paInt16,
            "channels": 1,
            "rate": sample_rate,
            "input": True,
            "frames_per_buffer": frames_per_buffer,
        }
        stream = pa.open(**open_kwargs)
        frames = []
        try:
            for _ in range(int(sample_rate / frames_per_buffer * max(1, seconds))):
                frames.append(stream.read(frames_per_buffer, exception_on_overflow=False))
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        pcm = b"".join(frames)
        if not pcm:
            return False

        # Ignore near-silent chunks to avoid unnecessary API calls.
        if audioop.rms(pcm, 2) < self._wake_rms_threshold:
            return False

        if self._detect_with_openwakeword(pcm, wakeword):
            return True

        text = ""
        rec = self._ensure_wake_recognizer()
        if rec is not None:
            try:
                import speech_recognition as sr
                audio = sr.AudioData(pcm, sample_rate, 2)
                text = rec.recognize_google(audio, language="en-US")
            except Exception:
                text = ""

        if not text:
            return False
        normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()
        wake = wakeword.lower().strip()
        wake_spaced = wake.replace("_", " ")
        wake_compact = wake_spaced.replace(" ", "")
        normalized_compact = normalized.replace(" ", "")
        return (
            wake in normalized.split()
            or wake in normalized
            or wake_spaced in normalized
            or wake_compact in normalized_compact
        )

    def play_activation_sound(self) -> None:
        if self._play_cue_file(self._wake_cue_path):
            return
        if platform.system() == "Windows":
            try:
                import winsound

                winsound.Beep(880, 90)
                time.sleep(0.03)
                winsound.Beep(1180, 120)
                return
            except Exception:
                pass

        pa = pyaudio.PyAudio()
        sample_rate = 22050
        duration = 0.18
        tone_hz = 1000.0
        frames = int(sample_rate * duration)
        buf = bytearray()
        for n in range(frames):
            # Simple sine-ish tone using triangle approximation, good enough for cue.
            phase = (n * tone_hz / sample_rate) % 1.0
            tri = 4 * abs(phase - 0.5) - 1
            amp = int(9000 * tri)
            buf += int(amp).to_bytes(2, byteorder="little", signed=True)

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True,
        )
        try:
            stream.write(bytes(buf))
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def play_listening_end_sound(self) -> None:
        if self._play_cue_file(self._sleep_cue_path):
            return
        if platform.system() == "Windows":
            try:
                import winsound

                winsound.Beep(980, 80)
                time.sleep(0.02)
                winsound.Beep(740, 120)
                return
            except Exception:
                pass

        pa = pyaudio.PyAudio()
        sample_rate = 22050
        duration = 0.16
        tone_hz = 760.0
        frames = int(sample_rate * duration)
        buf = bytearray()
        for n in range(frames):
            phase = (n * tone_hz / sample_rate) % 1.0
            tri = 4 * abs(phase - 0.5) - 1
            amp = int(7800 * tri)
            buf += int(amp).to_bytes(2, byteorder="little", signed=True)

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True,
        )
        try:
            stream.write(bytes(buf))
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _play_cue_file(self, cue_path: Path) -> bool:
        if not cue_path.exists():
            return False
        try:
            if platform.system() == "Windows":
                import winsound

                winsound.PlaySound(str(cue_path), winsound.SND_FILENAME)
                return True

            wf = wave.open(str(cue_path), "rb")
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
            )
            try:
                data = wf.readframes(1024)
                while data:
                    stream.write(data)
                    data = wf.readframes(1024)
            finally:
                stream.stop_stream()
                stream.close()
                pa.terminate()
                wf.close()
            return True
        except Exception:
            return False

    def speak_async(self, text: str) -> None:
        def _run():
            try:
                self.tts.speak(text)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
