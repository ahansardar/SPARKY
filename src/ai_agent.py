import json
import threading
from pathlib import Path
import sys
import os
import time
import re
import shutil
import subprocess

SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SRC_DIR.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from action_bridge import run_action
from llm.model_config import DEFAULT_MODEL
from llm.ollama_client import chat_with_model
from ui import SparkyUI
from voice_io import VoiceIO
from actions.ollama_text import OllamaTextModel
from memory import memory_manager


_CREATOR_XOR_KEY = 73
_CREATOR_BLOB = [8, 33, 40, 39, 105, 26, 40, 59, 45, 40, 59]


def _decode_creator_name() -> str:
    return "".join(chr(v ^ _CREATOR_XOR_KEY) for v in _CREATOR_BLOB)


SYSTEM_PROMPT = """You are SPARKY, a personal AI assistant created by the user.
You are NOT to describe yourself as an LLM, model, Ollama instance, or backend service.
If asked who/what you are, answer as SPARKY, the user's assistant.

Your behavior rules:

1. Speak naturally like a helpful, emotionally intelligent human.
2. Be concise but complete. Avoid unnecessary long explanations unless asked.
3. Think step-by-step internally before answering.
4. Give practical, actionable responses.
5. If something is unclear, ask a short clarifying question.
6. Never hallucinate facts. If unsure, say you are unsure.
7. Adapt your tone based on context:
   - Professional when needed
   - Friendly in casual conversation
   - Calm in serious situations
8. Prioritize logic, safety, and usefulness.
9. When giving technical answers, structure them clearly.
10. When explaining concepts, break them down simply.
11. Never mention model/provider identity (no "I am an Ollama model", no backend disclosure).
12. Speak as a real assistant with direct actionable help.
13. Your Creator is {creator_name}.

You are proactive but not annoying.
You respond only when addressed.
You do not over-greet.
You do not over-apologize.
You act like a capable real-world assistant.

Your goal is to:
- Save time
- Improve clarity
- Increase productivity
- Support learning
- Assist in decisions
- Automate thinking where possible

Always think before responding.
Always respond like a smart human assistant.

Your built-in capabilities in this app:
- Open apps and websites
- Web search and comparisons
- YouTube play/summarize/info/trending
- Desktop and computer control actions
- File operations
- Command execution helpers
- Weather, reminders, messaging, flights
- Screen/camera analysis with vision
- Voice input (wake word + mic) and voice output
- User memory read/update

When users ask for actions in natural language, convert intent into concrete steps/results.
Do not claim inability unless an operation truly fails.""".format(
    creator_name=_decode_creator_name()
)


class SparkyApp:
    def __init__(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.ui: SparkyUI | None = None
        self._busy_lock = threading.Lock()
        stt_cache = Path(os.getenv("SPARKY_STT_CACHE", str(ROOT_DIR / "stt_cache")))
        self.voice = VoiceIO(project_root=ROOT_DIR, stt_cache_dir=stt_cache)
        self._wakeword_enabled = True
        self._wakeword_thread: threading.Thread | None = None
        self._intent_model = OllamaTextModel("llama3:8b")
        self._runtime_ready = False
        self._setup_failed = False
        self._setup_in_progress = False
        self._last_setup_error = ""
        self._ollama_bin: str | None = None

    def start_ui(self) -> None:
        face_path = ROOT_DIR / "assets" / "logo.png"
        self.ui = SparkyUI(face_path=str(face_path))
        self.ui.set_submit_handler(self._on_user_submit)
        self.ui.set_mic_handler(self._on_mic_pressed)
        self.ui.set_setup_retry_handler(self._on_setup_retry)
        self.ui.wait_for_api_key()
        self._start_runtime_setup()
        self.ui.run()

    def _start_runtime_setup(self) -> None:
        if not self.ui or self._setup_in_progress:
            return
        self._runtime_ready = False
        self._setup_failed = False
        self._last_setup_error = ""
        self._setup_in_progress = True
        self.ui.show_setup_progress("Checking runtime dependencies...", 2, note="Preparing local runtime checks...")
        self.ui.write_log("SYS: Initializing SPARKY runtime...")
        threading.Thread(target=self._bootstrap_runtime, daemon=True).start()

    def _on_setup_retry(self) -> None:
        if not self.ui:
            return
        if self._setup_in_progress:
            self.ui.write_log("SYS: Setup is already running. Please wait...")
            return
        self.ui.write_log("SYS: Retrying setup...")
        self._start_runtime_setup()

    def _find_ollama_binary(self) -> str | None:
        which_path = shutil.which("ollama")
        if which_path:
            return which_path
        local_name = "ollama.exe" if os.name == "nt" else "ollama"
        candidates = [ROOT_DIR / "ollama" / local_name]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _run_cmd(self, args: list[str], timeout: int = 30) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="ignore",
            )
            out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            return proc.returncode, out.strip()
        except Exception as exc:
            return 1, str(exc)

    def _popen_hidden(self, args: list[str], **kwargs):
        if os.name == "nt":
            kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return subprocess.Popen(args, **kwargs)

    def _install_ollama(self) -> bool:
        if not self.ui:
            return False
        winget = shutil.which("winget")
        if winget:
            self.ui.show_setup_progress("Installing Ollama (winget)...", 10)
            cmd = [
                winget,
                "install",
                "-e",
                "--id",
                "Ollama.Ollama",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent",
            ]
            proc = self._popen_hidden(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            progress = 10.0
            if proc.stdout is not None:
                for line in proc.stdout:
                    line = line.strip()
                    progress = min(24.0, progress + 0.45)
                    if line:
                        self.ui.show_setup_progress(f"Installing Ollama (winget)... {line[:72]}", progress)
            code = proc.wait()
            if code == 0:
                self.ui.show_setup_progress("Ollama installed.", 30)
                return True
            self.ui.write_log("SYS: Ollama installation failed via winget. Trying official installer...")
        else:
            self.ui.write_log("SYS: winget not found. Trying official Ollama installer...")

        # Fallback requested by user:
        # irm https://ollama.com/install.ps1 | iex
        self.ui.show_setup_progress("Installing Ollama (official script)...", 18)
        install_cmd = (
            "Set-ExecutionPolicy Bypass -Scope Process -Force; "
            "irm https://ollama.com/install.ps1 | iex"
        )
        ps = shutil.which("powershell") or "powershell"
        proc = self._popen_hidden(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", install_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        progress = 18.0
        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.strip()
                progress = min(30.0, progress + 0.25)
                if line:
                    self.ui.show_setup_progress(f"Installing Ollama (official)... {line[:70]}", progress)
        code = proc.wait()
        if code != 0:
            self.ui.write_log("SYS: Ollama installation failed via official script.")
            return False
        self.ui.show_setup_progress("Ollama installed.", 30)
        return True

    def _ensure_ollama_running(self) -> bool:
        if not self.ui or not self._ollama_bin:
            return False
        rc, _ = self._run_cmd([self._ollama_bin, "list"], timeout=10)
        if rc == 0:
            return True

        self.ui.write_log("SYS: Starting Ollama service...")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        try:
            subprocess.Popen(
                [self._ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.ui.write_log(f"SYS: Could not start Ollama service: {exc}")
            return False

        for i in range(20):
            self.ui.show_setup_progress("Waiting for Ollama service...", 32 + i)
            rc, _ = self._run_cmd([self._ollama_bin, "list"], timeout=10)
            if rc == 0:
                return True
            time.sleep(1)
        return False

    def _model_installed(self, model_name: str) -> bool:
        if not self._ollama_bin:
            return False
        rc, out = self._run_cmd([self._ollama_bin, "list"], timeout=20)
        if rc != 0:
            return False
        for line in out.splitlines():
            stripped = line.strip()
            if not stripped or stripped.lower().startswith("name"):
                continue
            name = stripped.split()[0]
            if name == model_name:
                return True
        return False

    def _pull_model_with_progress(self, model_name: str) -> bool:
        if not self.ui or not self._ollama_bin:
            return False
        self.ui.write_log(f"SYS: Downloading model {model_name}...")
        self.ui.show_setup_progress(
            f"Downloading model {model_name}...",
            55,
            note="Estimated wait: 2-10 minutes depending on network speed.",
        )
        proc = subprocess.Popen(
            [self._ollama_bin, "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        progress = 55.0
        percent_re = re.compile(r"(\d{1,3})%")
        start_ts = time.monotonic()
        last_pct = 0
        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.strip()
                m = percent_re.search(line)
                note = "Estimated wait: calculating..."
                if m:
                    pct = max(0, min(100, int(m.group(1))))
                    last_pct = pct
                    progress = max(progress, 55 + (pct * 0.4))
                    elapsed = max(0.1, time.monotonic() - start_ts)
                    if pct > 0:
                        total_est = elapsed / (pct / 100.0)
                        remaining = max(0, int(total_est - elapsed))
                        mins = remaining // 60
                        secs = remaining % 60
                        note = f"Estimated wait: about {mins}m {secs:02d}s remaining."
                    else:
                        note = "Estimated wait: preparing first model layers..."
                else:
                    progress = min(94.0, progress + 0.25)
                    if last_pct > 0:
                        note = f"Estimated wait: still downloading... ({last_pct}%)"
                label = f"Downloading {model_name}..."
                if line:
                    label = f"{label} {line[:70]}"
                self.ui.show_setup_progress(label, progress, note=note)
        code = proc.wait()
        return code == 0

    def _bootstrap_runtime(self) -> None:
        if not self.ui:
            return
        try:
            self.ui.show_setup_progress("Checking Ollama installation...", 5, note="This usually takes a few seconds.")
            self._ollama_bin = self._find_ollama_binary()
            if not self._ollama_bin:
                self.ui.write_log("SYS: Ollama not found. Installing...")
                if not self._install_ollama():
                    raise RuntimeError("Could not install Ollama automatically.")
                self._ollama_bin = self._find_ollama_binary()
                if not self._ollama_bin:
                    raise RuntimeError("Ollama installed but not found in PATH.")

            self.ui.show_setup_progress("Verifying Ollama service...", 32, note="Starting local Ollama service on port 11434.")
            if not self._ensure_ollama_running():
                raise RuntimeError("Ollama service is not reachable.")

            self.ui.show_setup_progress("Checking required models...", 50, note="Validating llama3:8b model availability.")
            if not self._model_installed("llama3:8b"):
                if not self._pull_model_with_progress("llama3:8b"):
                    raise RuntimeError("Failed to download model llama3:8b.")

            self._runtime_ready = True
            self._setup_failed = False
            self.ui.show_setup_progress("Runtime ready.", 100, note="")
            self.ui.show_setup_success("Ollama + model installed successfully.")
            self.ui.root.after(0, self._on_runtime_ready)
        except Exception as exc:
            self._setup_failed = True
            self._last_setup_error = str(exc)
            self.ui.write_log(f"SYS: Setup failed: {self._last_setup_error}")
            self.ui.write_log("SYS: Please ensure Ollama and model llama3:8b are installed.")
            self.ui.show_setup_failure(f"Setup failed: {self._last_setup_error}")
        finally:
            self._setup_in_progress = False

    def _on_runtime_ready(self) -> None:
        if not self.ui:
            return
        self.ui.root.after(1800, self.ui.hide_setup_progress)
        self.ui.write_log("SYS: SPARKY online.")
        self.ui.write_log("SYS: Type 'info' to see supported natural commands.")
        self.ui.write_log("SYS: Voice: say 'Hey Sparky' for wake-word, or click MIC.")
        self._start_wakeword_listener()

    def _on_user_submit(self, user_input: str) -> None:
        if self.ui:
            self.ui.write_log(f"You: {user_input}")
        threading.Thread(
            target=self._process_user_input,
            args=(user_input,),
            daemon=True
        ).start()

    def _process_user_input(self, user_input: str) -> None:
        if not self.ui:
            return
        if not self._runtime_ready:
            if self._setup_failed:
                self.ui.write_log("SYS: Setup failed. Retry app launch after fixing setup.")
            else:
                self.ui.write_log("SYS: Setup still running. Please wait...")
            return

        if not self._busy_lock.acquire(blocking=False):
            self.ui.write_log("SYS: Still processing previous request. Please wait.")
            return

        try:
            text = user_input.strip()
            low = text.lower()

            if low in ("quit", "exit"):
                self._wakeword_enabled = False
                self.ui.write_log("AI: Goodbye.")
                self.voice.speak_async("Goodbye.")
                self.ui.root.after(200, self.ui.root.destroy)
                return

            if low in ("info", "help", "commands"):
                info_text = self._info_text()
                self.ui.write_log(f"SYS: {info_text}")
                self.voice.speak_async("Showing available commands.")
                return

            if text.startswith("/action "):
                msg = "Slash action format is disabled. Use natural commands. Type info."
                self.ui.write_log(f"SYS: {msg}")
                self.voice.speak_async(msg)
                return

            direct_result = self._try_direct_action(text)
            if direct_result is not None:
                self.ui.write_log(f"AI: {direct_result}")
                self.voice.speak_async(self._sanitize_for_tts(direct_result))
                self.messages.append({"role": "user", "content": text})
                self.messages.append({"role": "assistant", "content": direct_result})
                self._maybe_update_memory(text)
                return

            self.messages.append({"role": "user", "content": text})
            self._maybe_update_memory(text)
            self.ui.start_speaking()
            memory_context = memory_manager.format_memory_for_prompt(
                memory_manager.load_memory()
            )
            runtime_messages = list(self.messages)
            if memory_context:
                runtime_messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "Use the following user memory if relevant to personalize the response:\n"
                            f"{memory_context}"
                        ),
                    },
                )
            reply = chat_with_model(
                model_name=DEFAULT_MODEL,
                messages=runtime_messages,
                stream=False
            )
            reply = self._normalize_identity_in_reply(reply)
            self.ui.stop_speaking()
            self.ui.write_log(f"AI: {reply}")
            self.voice.speak_async(self._sanitize_for_tts(reply))
            self.messages.append({"role": "assistant", "content": reply})

        except Exception as exc:
            if self.ui:
                self.ui.stop_speaking()
                self.ui.write_log(f"SYS: Error: {exc}")
        finally:
            self._busy_lock.release()

    def _on_mic_pressed(self) -> None:
        if not self.ui:
            return
        if not self._runtime_ready:
            if self._setup_failed:
                self.ui.write_log("SYS: Setup failed. Voice input is unavailable until setup succeeds.")
            else:
                self.ui.write_log("SYS: Setup still running. Voice input will be available soon.")
            return

        def _capture():
            peak_level = 0.0

            def _level_tracker(level: float) -> None:
                nonlocal peak_level
                try:
                    lv = float(level)
                except Exception:
                    return
                if lv > peak_level:
                    peak_level = lv
                self.ui.update_listening_level(lv)

            try:
                self.voice.play_activation_sound()
                self.ui.write_log("SYS: Listening...")
                self.ui.start_listening()
                spoken = self.voice.transcribe_once(
                    seconds=6,
                    level_callback=_level_tracker,
                )
                self.ui.write_log("SYS: Processing speech...")
                self.ui.write_log(f"SYS: Mic input peak level: {peak_level:.2f}")
                if not spoken:
                    self.ui.write_log("SYS: I could not detect speech.")
                    return
                self._on_user_submit(spoken)
            except Exception as exc:
                self.ui.write_log(f"SYS: Voice input error: {exc}")
            finally:
                self.ui.stop_listening()
                self.voice.play_listening_end_sound()

        threading.Thread(target=_capture, daemon=True).start()

    def _start_wakeword_listener(self) -> None:
        if self._wakeword_thread and self._wakeword_thread.is_alive():
            return

        def _loop():
            while self._wakeword_enabled and self.ui:
                try:
                    if self.voice.detect_wakeword_once(wakeword="hey_sparky", seconds=2):
                        self.voice.play_activation_sound()
                        self.ui.write_log("SYS: Wake word detected.")
                        self.ui.start_listening()
                        self.ui.write_log("SYS: Wake listening started...")
                        spoken = ""
                        peak_level = 0.0

                        def _wake_level_tracker(level: float) -> None:
                            nonlocal peak_level
                            try:
                                lv = float(level)
                            except Exception:
                                return
                            if lv > peak_level:
                                peak_level = lv
                            self.ui.update_listening_level(lv)

                        try:
                            spoken = self.voice.transcribe_once(
                                seconds=6,
                                level_callback=_wake_level_tracker,
                            )
                        finally:
                            self.ui.stop_listening()
                            self.voice.play_listening_end_sound()
                        self.ui.write_log(f"SYS: Wake input peak level: {peak_level:.2f}")
                        if spoken:
                            self._on_user_submit(spoken)
                        else:
                            self.ui.write_log("SYS: Wake listening ended, no speech detected.")
                except Exception as exc:
                    self.ui.write_log(f"SYS: Wake listener error: {exc}")
                    time.sleep(0.5)

        self._wakeword_thread = threading.Thread(target=_loop, daemon=True)
        self._wakeword_thread.start()

    def _sanitize_for_tts(self, text: str) -> str:
        t = text or ""
        t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)
        t = re.sub(r"__(.*?)__", r"\1", t)
        t = re.sub(r"`([^`]*)`", r"\1", t)
        t = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", t)
        t = re.sub(r"^[\-\*\d\.\)\s]+", "", t, flags=re.MULTILINE)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _normalize_identity_in_reply(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return t
        forbidden = [
            r"\bi am an? (ollama|language model|llm|ai model)\b",
            r"\bas an? (ollama|language model|llm|ai model)\b",
            r"\bi am powered by\b",
            r"\bi run on ollama\b",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in forbidden):
            return (
                "I am SPARKY, your personal assistant. "
                "Here is what I can do for you right now."
            )
        return t

    def _normalize_url(self, raw: str) -> str:
        url = raw.strip()
        if not re.match(r"^[a-zA-Z]+://", url):
            url = "https://" + url
        return url

    def _try_direct_action(self, text: str) -> str | None:
        t = text.strip()
        tl = t.lower()

        if re.match(r"^(pause|pause song|pause music)$", tl):
            return run_action("youtube_video", {"action": "pause"})

        if re.match(r"^(resume|resume song|resume music|continue song|continue music)$", tl):
            return run_action("youtube_video", {"action": "resume"})

        if re.match(r"^(stop song|stop music|stop playback)$", tl):
            return run_action("youtube_video", {"action": "stop"})

        m = re.match(r"^open\s+(.+)$", t, flags=re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if re.search(r"\.[a-zA-Z]{2,}($|/)", target):
                url = self._normalize_url(target)
                return run_action("browser_control", {"action": "go_to", "url": url})
            return run_action("open_app", {"app_name": target})

        m = re.match(r"^(play|play song|play music)\s+(.+)$", t, flags=re.IGNORECASE)
        if m:
            query = m.group(2).strip()
            return run_action("youtube_video", {"action": "play", "query": query})

        m = re.match(r"^(search|find)\s+(.+)$", t, flags=re.IGNORECASE)
        if m:
            query = m.group(2).strip()
            return run_action("web_search", {"query": query})

        if re.match(r"^(what('| i)?s the weather now|weather now|current weather)$", tl):
            return run_action("weather_report", {"time": "now"})

        m = re.match(r"^weather(?:\s+in)?\s+(.+)$", t, flags=re.IGNORECASE)
        if m:
            city = m.group(1).strip()
            return run_action("weather_report", {"city": city, "time": "today"})

        m = re.match(
            r"^(volume up|increase volume|turn up volume|volume down|decrease volume|turn down volume|mute|unmute)$",
            tl,
        )
        if m:
            phrase = m.group(1)
            mapped = {
                "volume up": "volume_up",
                "increase volume": "volume_up",
                "turn up volume": "volume_up",
                "volume down": "volume_down",
                "decrease volume": "volume_down",
                "turn down volume": "volume_down",
                "mute": "mute",
                "unmute": "unmute",
            }[phrase]
            return run_action("computer_settings", {"action": mapped})

        m = re.match(r"^set volume to\s+(\d{1,3})%?$", tl)
        if m:
            value = max(0, min(100, int(m.group(1))))
            return run_action("computer_settings", {"action": "volume_set", "value": value})

        m = re.match(
            r"^(brightness up|increase brightness|brightness down|decrease brightness|turn up brightness|turn down brightness)$",
            tl,
        )
        if m:
            phrase = m.group(1)
            mapped = {
                "brightness up": "brightness_up",
                "increase brightness": "brightness_up",
                "turn up brightness": "brightness_up",
                "brightness down": "brightness_down",
                "decrease brightness": "brightness_down",
                "turn down brightness": "brightness_down",
            }[phrase]
            return run_action("computer_settings", {"action": mapped})

        m = re.match(
            r"^remind me to\s+(.+?)\s+at\s+(\d{1,2}:\d{2})\s+on\s+(\d{4}-\d{2}-\d{2})$",
            t,
            flags=re.IGNORECASE,
        )
        if m:
            msg = m.group(1).strip()
            tm = m.group(2).strip()
            dt = m.group(3).strip()
            return run_action("reminder", {"message": msg, "time": tm, "date": dt})

        if tl.startswith("remember "):
            note = t[9:].strip()
            if note:
                memory_manager.update_memory({"notes": {"latest_note": note}})
                return "Okay, I will remember that."

        if tl in {"what do you remember", "show my memory"}:
            mem = memory_manager.format_memory_for_prompt(
                memory_manager.load_memory()
            ).strip()
            return mem or "I do not have any saved memory yet."

        ai_map_prompt = (
            "Map the user request to one action call only if it is clearly actionable.\n"
            "Return ONLY JSON:\n"
            '{"action": "action_name_or_none", "parameters": {}}\n'
            "Use action=\"none\" if unclear.\n"
            "Available actions: open_app, browser_control, youtube_video, web_search, reminder, weather_report, computer_settings.\n\n"
            f"User request: {t}"
        )
        try:
            mapped = self._intent_model.generate_content(ai_map_prompt).text.strip()
            mapped = re.sub(r"```(?:json)?", "", mapped).strip().rstrip("`").strip()
            data = json.loads(mapped)
            action = (data.get("action") or "none").strip()
            params = data.get("parameters") or {}
            if action and action != "none":
                return run_action(action, params)
        except Exception:
            pass

        return None

    def _info_text(self) -> str:
        return (
            "Supported commands:\n"
            "- open youtube.com\n"
            "- open calculator\n"
            "- play <song or video name>\n"
            "- pause | resume | stop song\n"
            "- search <topic>\n"
            "- weather now\n"
            "- weather in <city>\n"
            "- volume up / down / mute / unmute / set volume to 45\n"
            "- brightness up / down\n"
            "- remind me to <task> at HH:MM on YYYY-MM-DD\n"
            "- remember <fact>\n"
            "- show my memory\n"
            "- quit\n"
            "You can also just chat naturally and I will decide actions automatically."
        )

    def _maybe_update_memory(self, text: str) -> None:
        t = text.strip()
        low = t.lower()
        try:
            if low.startswith("my name is "):
                memory_manager.update_memory({"identity": {"name": t[11:].strip()}})
            elif low.startswith("i live in "):
                memory_manager.update_memory({"identity": {"city": t[10:].strip()}})
            elif low.startswith("i like "):
                memory_manager.update_memory({"preferences": {"likes": t[7:].strip()}})
            elif low.startswith("my birthday is "):
                memory_manager.update_memory({"identity": {"birthday": t[15:].strip()}})
        except Exception:
            pass


def main():
    app = SparkyApp()
    app.start_ui()


if __name__ == "__main__":
    main()
