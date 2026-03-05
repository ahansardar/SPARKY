import threading
import time
import tkinter as tk
import io
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

SYSTEM_NAME = "SPARKY"
MODEL_BADGE = "Smart Personal Assistant for Real-time Knowledge and Productivity"


class SparkyUI:
    def __init__(self, face_path, size=None):
        self._main_thread_id = threading.get_ident()
        self._submit_handler = None
        self._mic_handler = None
        self._setup_retry_handler = None
        self._api_key_ready = True
        self._listening = False
        self._wave_level = 0.0
        self._wave_job = None
        self._listen_timeout_job = None
        self._icon_refs = {}
        self._setup_visible = False

        self.root = tk.Tk()
        self.root.title("SPARKY")
        self.root.configure(bg="#f3f5f8")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(sw - 120, 980)
        h = min(sh - 120, 760)
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.minsize(900, 680)

        self._build_styles()
        self._build_layout(face_path, w, h)

        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Header.TFrame", background="#ffffff")
        style.configure("Body.TFrame", background="#f3f5f8")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Input.TFrame", background="#ffffff")

        style.configure(
            "Title.TLabel",
            background="#ffffff",
            foreground="#1e2a3a",
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "SubTitle.TLabel",
            background="#ffffff",
            foreground="#5d6b7d",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Status.TLabel",
            background="#ffffff",
            foreground="#2c8a3d",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background="#f3f5f8",
            foreground="#6f7e90",
            font=("Segoe UI", 9),
        )

    def _build_layout(self, face_path, w: int, h: int):
        container = ttk.Frame(self.root, style="Body.TFrame", padding=16)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Header.TFrame", padding=(16, 12))
        header.pack(fill="x")

        assets_dir = Path(face_path).resolve().parent
        logo_path = assets_dir / "logo.png"
        text_logo_path = assets_dir / "text.png"
        self._set_window_logo(logo_path)

        avatar = self._load_avatar(str(logo_path if logo_path.exists() else face_path), 52)
        self.avatar_label = tk.Label(header, image=avatar, bg="#ffffff", bd=0)
        self.avatar_label.image = avatar
        self.avatar_label.pack(side="left")

        title_wrap = ttk.Frame(header, style="Header.TFrame")
        title_wrap.pack(side="left", padx=12)
        title_image = self._load_title_image(text_logo_path, max_w=260, max_h=34)
        if title_image is not None:
            title_img_label = tk.Label(title_wrap, image=title_image, bg="#ffffff", bd=0)
            title_img_label.image = title_image
            title_img_label.pack(anchor="w")
            self._icon_refs["title_text"] = title_image
        else:
            ttk.Label(title_wrap, text=SYSTEM_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_wrap, text=MODEL_BADGE, style="SubTitle.TLabel").pack(anchor="w")

        self.status_label = ttk.Label(header, text="Online", style="Status.TLabel")
        self.status_label.pack(side="right")

        self.setup_frame = ttk.Frame(container, style="Body.TFrame")
        self.setup_label = ttk.Label(self.setup_frame, text="", style="Hint.TLabel")
        self.setup_label.pack(anchor="w")
        progress_row = ttk.Frame(self.setup_frame, style="Body.TFrame")
        progress_row.pack(fill="x", pady=(4, 0))
        self.setup_progress = ttk.Progressbar(
            progress_row,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.setup_progress.pack(side="left", fill="x", expand=True)
        self.setup_percent_label = ttk.Label(
            progress_row,
            text="0%",
            style="Hint.TLabel",
        )
        self.setup_percent_label.pack(side="right", padx=(10, 0))
        self.setup_note_label = ttk.Label(
            self.setup_frame,
            text="",
            style="Hint.TLabel",
        )
        self.setup_note_label.pack(anchor="w", pady=(2, 0))
        self.setup_banner_label = ttk.Label(
            self.setup_frame,
            text="",
            style="Hint.TLabel",
        )
        self.setup_banner_label.pack(anchor="w", pady=(6, 0))
        self.setup_retry_btn = tk.Button(
            self.setup_frame,
            text="Retry Setup",
            command=self._on_setup_retry,
            bg="#fce8e6",
            fg="#8a1f1f",
            activebackground="#f8d7d3",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )

        body = ttk.Frame(container, style="Body.TFrame")
        body.pack(fill="both", expand=True, pady=(14, 10))

        chat_card = ttk.Frame(body, style="Card.TFrame", padding=10)
        chat_card.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            chat_card,
            bg="#ffffff",
            fg="#243447",
            insertbackground="#243447",
            borderwidth=0,
            wrap="word",
            font=("Segoe UI", 11),
            padx=10,
            pady=10,
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(chat_card, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

        self.log_text.tag_config("you", foreground="#1f4aa8", font=("Segoe UI", 11, "bold"))
        self.log_text.tag_config("ai", foreground="#1d7a4a", font=("Segoe UI", 11, "bold"))
        self.log_text.tag_config("sys", foreground="#7a5a10", font=("Segoe UI", 10, "italic"))
        self.log_text.tag_config("body", foreground="#243447", font=("Segoe UI", 11))

        hint = ttk.Label(
            body,
            text="Tip: type naturally, or use actions / say 'Hey Sparky' for wake word.",
            style="Hint.TLabel",
        )
        hint.pack(anchor="w", pady=(8, 0))

        input_card = ttk.Frame(container, style="Input.TFrame", padding=10)
        input_card.pack(fill="x")

        self.input_entry = tk.Entry(
            input_card,
            bg="#f7f9fc",
            fg="#1f2d3d",
            insertbackground="#1f2d3d",
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 11),
        )
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(4, 10))
        self.input_entry.bind("<Return>", lambda _e: self._on_submit())

        mic_icon = self._load_button_icon(assets_dir / "mic.svg", 24)
        send_icon = self._load_button_icon(assets_dir / "send.svg", 24)

        self.mic_btn = tk.Button(
            input_card,
            text="" if mic_icon else "MIC",
            image=mic_icon,
            command=self._on_mic,
            bg="#eef3ff",
            fg="#23408f",
            activebackground="#dfe7fb",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=10,
            cursor="hand2",
        )
        if mic_icon:
            self._icon_refs["mic"] = mic_icon
        self.mic_btn.pack(side="right", padx=(0, 8))

        self.send_btn = tk.Button(
            input_card,
            text="" if send_icon else "SEND",
            image=send_icon,
            command=self._on_submit,
            bg="#2a5bd7",
            fg="#ffffff",
            activebackground="#1f4ec2",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=10,
            cursor="hand2",
        )
        if send_icon:
            self._icon_refs["send"] = send_icon
        self.send_btn.pack(side="right")

        self.wave_canvas = tk.Canvas(
            container,
            height=36,
            bg="#eef3ff",
            highlightthickness=1,
            highlightbackground="#c7d5f6",
            bd=0,
        )
        self.wave_canvas.pack(fill="x", pady=(6, 0))
        self.wave_canvas.bind("<Configure>", lambda _e: self._draw_idle_wave())
        self._draw_idle_wave()

    def _load_avatar(self, face_path, size_px: int):
        try:
            img = Image.open(face_path).convert("RGB").resize((size_px, size_px), Image.LANCZOS)
        except Exception:
            img = Image.new("RGB", (size_px, size_px), color="#c7d2e5")
        return ImageTk.PhotoImage(img)

    def _load_title_image(self, image_path: Path, max_w: int, max_h: int):
        try:
            img = Image.open(image_path).convert("RGBA")
            w, h = img.size
            if w <= 0 or h <= 0:
                return None
            scale = min(max_w / w, max_h / h)
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            img = img.resize((nw, nh), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _set_window_logo(self, logo_path: Path):
        try:
            img = Image.open(logo_path).convert("RGBA").resize((32, 32), Image.LANCZOS)
            icon = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, icon)
            self._icon_refs["app_logo"] = icon
        except Exception:
            pass

    def _load_button_icon(self, icon_path: Path, size_px: int):
        try:
            if icon_path.suffix.lower() == ".svg":
                try:
                    import cairosvg  # type: ignore
                    png_data = cairosvg.svg2png(
                        url=str(icon_path),
                        output_width=size_px,
                        output_height=size_px,
                    )
                    img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                except Exception:
                    return None
            else:
                img = Image.open(icon_path).convert("RGBA")
                img = img.resize((size_px, size_px), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _set_status(self, text: str, color: str):
        self.status_label.configure(text=text, foreground=color)

    def write_log(self, text: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.write_log, text)
            return

        raw = (text or "").strip()
        if not raw:
            return

        if raw.lower().startswith("you:"):
            role_tag = "you"
            body = raw[4:].strip()
            role = "You"
        elif raw.lower().startswith("ai:"):
            role_tag = "ai"
            body = raw[3:].strip()
            role = "Sparky"
        else:
            role_tag = "sys"
            body = raw[4:].strip() if raw.lower().startswith("sys:") else raw
            role = "System"

        stamp = time.strftime("%H:%M")
        line_header = f"[{stamp}] {role}: "

        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, line_header, role_tag)
        self.log_text.insert(tk.END, f"{body}\n", "body")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def start_speaking(self):
        self.speaking = True
        self._set_status("Responding", "#a36b00")

    def stop_speaking(self):
        self.speaking = False
        self._set_status("Online", "#2c8a3d")

    def start_listening(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.start_listening)
            return
        self._listening = True
        self._wave_level = 0.0
        self._set_status("Listening", "#1f4ec2")
        if self._listen_timeout_job is not None:
            try:
                self.root.after_cancel(self._listen_timeout_job)
            except Exception:
                pass
        # Safety net: never stay in listening state indefinitely.
        self._listen_timeout_job = self.root.after(6500, self.stop_listening)
        self._animate_wave()

    def stop_listening(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.stop_listening)
            return
        self._listening = False
        if self._listen_timeout_job is not None:
            try:
                self.root.after_cancel(self._listen_timeout_job)
            except Exception:
                pass
            self._listen_timeout_job = None
        if self._wave_job is not None:
            try:
                self.root.after_cancel(self._wave_job)
            except Exception:
                pass
            self._wave_job = None
        self._draw_idle_wave()
        self._set_status("Online", "#2c8a3d")

    def update_listening_level(self, level: float):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.update_listening_level, level)
            return
        self._wave_level = max(0.0, min(1.0, float(level)))

    def _draw_idle_wave(self):
        self.wave_canvas.delete("all")
        w = max(80, self.wave_canvas.winfo_width())
        h = max(1, self.wave_canvas.winfo_height())
        text_id = self.wave_canvas.create_text(
            10,
            h // 2,
            text="Input waveform",
            anchor="w",
            fill="#5f6f8f",
            font=("Segoe UI", 9),
        )
        bbox = self.wave_canvas.bbox(text_id)
        line_start = (bbox[2] + 10) if bbox else 120
        self.wave_canvas.create_line(line_start, h // 2, w - 8, h // 2, fill="#9fb6ef", width=2)

    def _animate_wave(self):
        if not self._listening:
            return
        self.wave_canvas.delete("all")
        w = max(80, self.wave_canvas.winfo_width())
        h = max(1, self.wave_canvas.winfo_height())
        self.wave_canvas.create_rectangle(0, 0, w, h, fill="#e8f0ff", outline="")
        text_id = self.wave_canvas.create_text(
            10,
            h // 2,
            text="Listening...",
            anchor="w",
            fill="#2a5bd7",
            font=("Segoe UI", 9, "bold"),
        )
        bbox = self.wave_canvas.bbox(text_id)
        left = (bbox[2] + 10) if bbox else 120
        right_pad = 8
        usable_w = max(40, w - left - right_pad)
        bars = max(10, min(36, usable_w // 6))
        gap = 2
        bar_w = max(2, (usable_w - (bars + 1) * gap) // bars)
        center = h / 2
        max_amp = max(4, h * 0.46)
        amp = self._wave_level * max_amp

        x = left + gap
        for i in range(bars):
            falloff = 1.0 - abs(i - bars / 2) / (bars / 2)
            bar_amp = max(2, amp * (0.35 + 0.65 * falloff))
            self.wave_canvas.create_rectangle(
                x,
                center - bar_amp,
                x + bar_w,
                center + bar_amp,
                fill="#2a5bd7",
                outline="",
            )
            x += bar_w + gap
        self._wave_level *= 0.8
        self._wave_job = self.root.after(33, self._animate_wave)

    def _api_keys_exist(self):
        return True

    def wait_for_api_key(self):
        return

    def _show_setup_ui(self):
        return

    def _save_api_keys(self):
        return

    def set_submit_handler(self, fn):
        self._submit_handler = fn

    def set_mic_handler(self, fn):
        self._mic_handler = fn

    def set_setup_retry_handler(self, fn):
        self._setup_retry_handler = fn

    def _on_submit(self):
        if self._submit_handler is None:
            return
        text = self.input_entry.get().strip()
        if not text:
            return
        self.input_entry.delete(0, tk.END)
        self._submit_handler(text)

    def _on_mic(self):
        if self._mic_handler is None:
            return
        self._mic_handler()

    def run(self):
        self.input_entry.focus_set()
        self.root.mainloop()

    def show_setup_progress(self, text: str, value: float, note: str | None = None):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_setup_progress, text, value, note)
            return
        if not self._setup_visible:
            self.setup_frame.pack(fill="x", pady=(2, 10))
            self._setup_visible = True
        self.setup_label.configure(text=str(text))
        self.setup_banner_label.configure(text="", foreground="#6f7e90")
        self.setup_retry_btn.pack_forget()
        try:
            v = max(0, min(100, float(value)))
            self.setup_progress.configure(value=v)
            self.setup_percent_label.configure(text=f"{int(v)}%")
        except Exception:
            self.setup_progress.configure(value=0)
            self.setup_percent_label.configure(text="0%")
        self.setup_note_label.configure(text=(note or ""))
        self.root.update_idletasks()

    def show_setup_success(self, message: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_setup_success, message)
            return
        if not self._setup_visible:
            self.setup_frame.pack(fill="x", pady=(2, 10))
            self._setup_visible = True
        self.setup_progress.configure(value=100)
        self.setup_percent_label.configure(text="100%")
        self.setup_note_label.configure(text="")
        self.setup_banner_label.configure(text=message, foreground="#1f7a45")
        self.setup_retry_btn.pack_forget()
        self.root.update_idletasks()

    def show_setup_failure(self, message: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_setup_failure, message)
            return
        if not self._setup_visible:
            self.setup_frame.pack(fill="x", pady=(2, 10))
            self._setup_visible = True
        self.setup_banner_label.configure(text=message, foreground="#8a1f1f")
        self.setup_note_label.configure(text="Fix issue and click Retry Setup.")
        self.setup_retry_btn.pack(anchor="w", pady=(6, 0))
        self.root.update_idletasks()

    def hide_setup_progress(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.hide_setup_progress)
            return
        if self._setup_visible:
            self.setup_frame.pack_forget()
            self._setup_visible = False

    def _on_setup_retry(self):
        if self._setup_retry_handler is None:
            return
        self._setup_retry_handler()
