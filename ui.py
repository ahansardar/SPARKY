import threading
import time
import tkinter as tk
import io
import re
import ctypes
import os
from datetime import datetime
import json
from pathlib import Path
from tkinter import ttk, filedialog
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageTk
from system_stats import collect_system_stats, format_system_stats_report, internet_speed_test_mbps

SYSTEM_NAME = "SPARKY"
MODEL_BADGE = "Smart Personal Assistant for Real-time Knowledge and Productivity"


class SparkyUI:
    def __init__(self, face_path, size=None):
        self._main_thread_id = threading.get_ident()
        self._submit_handler = None
        self._mic_handler = None
        self._mic_mute_toggle_handler = None
        self._tts_volume_handler = None
        self._pdf_handler = None
        self._pdf_discard_handler = None
        self._setup_retry_handler = None
        self._playback_state_handler = None
        self._playback_control_handler = None
        self._update_now_handler = None
        self._update_later_handler = None
        self._api_key_ready = True
        self._listening = False
        self._listen_timeout_job = None
        self._processing = False
        self._processing_job = None
        self._loading_frames = []
        self._loading_frame_idx = 0
        self._icon_refs = {}
        self._setup_visible = False
        self._placeholder_text = "Type a message, command, or question..."
        self._placeholder_active = False
        self._pending_pdf_path = ""
        self._pdf_card_icon = None
        self._mic_muted = False
        self._control_pane = None
        self._monitor_pane = None
        self._monitor_labels = {}
        self._monitor_job = None
        self._net_snapshot = None
        self._speed_test_result = None
        self._speed_test_ts = 0.0
        self._speed_test_inflight = False
        self._always_on_top_enabled = False
        self._always_on_top_var = None
        self._mini_window = None
        self._mini_log_text = None
        self._mini_input_entry = None
        self._mini_status_label = None
        self._playback_frame = None
        self._playback_thumb_label = None
        self._playback_title_label = None
        self._playback_artist_label = None
        self._playback_progress = None
        self._playback_time_label = None
        self._playback_btn_prev = None
        self._playback_btn_toggle = None
        self._playback_btn_next = None
        self._playback_thumb_image = None
        self._playback_poll_job = None
        self._playback_visible = False
        self._playback_last_thumb_url = ""
        self._suppress_unmap_handler = False
        self._update_window = None
        self._update_title_label = None
        self._update_message_label = None
        self._update_progress = None
        self._update_note_label = None
        self._update_now_btn = None
        self._update_later_btn = None
        self._font_family = "Poppins"
        self._status_palette = {
            "online": "#eaf7ef",
            "listening": "#eef3ff",
            "responding": "#fff5e7",
            "processing": "#eef3ff",
        }

        self.root = tk.Tk()
        self.root.title("SPARKY")
        self.root.configure(bg="#f6f8fc")
        self.root.resizable(False, False)
        self._init_font_family()
        self._always_on_top_var = tk.BooleanVar(master=self.root, value=False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(sw - 120, 980)
        h = min(sh - 120, 760)
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.minsize(900, 680)

        self._build_styles()
        self._build_layout(face_path, w, h)
        self._playback_poll_job = self.root.after(700, self._refresh_playback_pane)

        self.root.protocol("WM_DELETE_WINDOW", self._on_main_close)
        self.root.bind("<Unmap>", self._on_root_unmap)
        self.root.bind("<Map>", self._on_root_map)

    def _init_font_family(self):
        fonts_dir = Path(__file__).resolve().parent / "fonts"
        if os.name == "nt" and fonts_dir.exists():
            try:
                FR_PRIVATE = 0x10
                for font_file in fonts_dir.glob("Poppins-*.ttf"):
                    ctypes.windll.gdi32.AddFontResourceExW(str(font_file), FR_PRIVATE, 0)  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            import tkinter.font as tkfont

            families = {name.lower() for name in tkfont.families(self.root)}
            if "poppins" not in families:
                self._font_family = "Segoe UI"
        except Exception:
            self._font_family = "Segoe UI"
        self.root.option_add("*Font", (self._font_family, 10))

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Header.TFrame", background="#ffffff")
        style.configure("Body.TFrame", background="#f6f8fc")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Input.TFrame", background="#ffffff")

        style.configure(
            "Title.TLabel",
            background="#ffffff",
            foreground="#1e2a3a",
            font=("Poppins", 16, "bold"),
        )
        style.configure(
            "SubTitle.TLabel",
            background="#ffffff",
            foreground="#5d6b7d",
            font=("Poppins", 10),
        )
        style.configure(
            "Status.TLabel",
            background="#ffffff",
            foreground="#2c8a3d",
            font=("Poppins", 10, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background="#f6f8fc",
            foreground="#6a7689",
            font=("Poppins", 9),
        )

    def _build_layout(self, face_path, w: int, h: int):
        container = ttk.Frame(self.root, style="Body.TFrame", padding=16)
        container.pack(fill="both", expand=True)

        header_shell = tk.Frame(
            container,
            bg="#eef2fb",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
        )
        header_shell.pack(fill="x")
        header = ttk.Frame(header_shell, style="Header.TFrame", padding=(16, 10))
        header.pack(fill="x")

        assets_dir = Path(face_path).resolve().parent
        self._assets_dir = assets_dir
        logo_path = assets_dir / "logo.png"
        text_logo_path = assets_dir / "text.png"
        pdf_card_candidates = sorted(assets_dir.glob("pdf_card.*"))
        loading_icon_path = assets_dir / "loading.svg"
        self._set_window_logo(logo_path)
        if pdf_card_candidates:
            self._pdf_card_icon = self._load_button_icon(pdf_card_candidates[0], 20)
            if self._pdf_card_icon is not None:
                self._icon_refs["pdf_card"] = self._pdf_card_icon
        if self._pdf_card_icon is None:
            self._pdf_card_icon = self._load_button_icon(assets_dir / "pdf.svg", 20)
            if self._pdf_card_icon is not None:
                self._icon_refs["pdf_card_fallback"] = self._pdf_card_icon
        self._loading_frames = self._load_rotating_icon_frames(loading_icon_path, 16)
        if self._loading_frames:
            self._icon_refs["loading_frames"] = self._loading_frames

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

        header_right = tk.Frame(header, bg="#ffffff", bd=0)
        header_right.pack(side="right")

        self.status_label = tk.Label(
            header_right,
            text="Online",
            fg="#2c8a3d",
            bg=self._status_palette["online"],
            font=("Poppins", 10, "bold"),
            padx=10,
            pady=5,
            bd=0,
            compound="left",
        )
        self.status_label.pack(side="left")

        settings_icon = self._load_button_icon(assets_dir / "settings.svg", 18)
        if settings_icon is not None:
            self._icon_refs["settings"] = settings_icon
        monitor_icon = self._load_button_icon(assets_dir / "system_res.svg", 18)
        if monitor_icon is not None:
            self._icon_refs["system_res"] = monitor_icon
        self.monitor_btn = tk.Button(
            header_right,
            text="" if monitor_icon else "Monitor",
            image=monitor_icon,
            command=self._toggle_monitor_pane,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            bd=0,
            font=("Poppins", 9, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.monitor_btn.pack(side="left", padx=(8, 0))
        self._attach_button_hover(self.monitor_btn, "#ffffff", "#f4f7ff")

        self.settings_btn = tk.Button(
            header_right,
            text="" if settings_icon else "Settings",
            image=settings_icon,
            command=self._toggle_control_pane,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            bd=0,
            font=("Poppins", 9, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.settings_btn.pack(side="left", padx=(8, 0))
        self._attach_button_hover(self.settings_btn, "#ffffff", "#f4f7ff")

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
            font=("Poppins", 9, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )

        tiles_row = ttk.Frame(container, style="Body.TFrame")
        tiles_row.pack(fill="x", pady=(10, 0))

        tile_specs = [
            ("Time", "time"),
            ("Date", "date"),
            ("Weather", "weather"),
        ]
        for i, (title, kind) in enumerate(tile_specs):
            tile = tk.Frame(
                tiles_row,
                bg="#ffffff",
                highlightthickness=1,
                highlightbackground="#e4e9f4",
                bd=0,
                padx=12,
                pady=10,
            )
            tile.pack(side="left", fill="x", expand=True, padx=(0, 8 if i < 2 else 0))
            tk.Label(
                tile,
                text=title,
                bg="#ffffff",
                fg="#6d788b",
                font=("Poppins", 8),
                anchor="w",
            ).pack(anchor="w")
            if kind == "time":
                self.time_value_label = tk.Label(
                    tile,
                    text="--:--:--",
                    bg="#ffffff",
                    fg="#183463",
                    font=("Poppins", 14, "bold"),
                    anchor="w",
                )
                self.time_value_label.pack(anchor="w", pady=(3, 1))
                self.time_tz_label = tk.Label(
                    tile,
                    text="--",
                    bg="#ffffff",
                    fg="#51607a",
                    font=("Poppins", 9),
                    anchor="w",
                )
                self.time_tz_label.pack(anchor="w")
            elif kind == "date":
                self.date_value_label = tk.Label(
                    tile,
                    text="--",
                    bg="#ffffff",
                    fg="#183463",
                    font=("Poppins", 14, "bold"),
                    anchor="w",
                )
                self.date_value_label.pack(anchor="w", pady=(3, 1))
                self.date_weekday_label = tk.Label(
                    tile,
                    text="--",
                    bg="#ffffff",
                    fg="#51607a",
                    font=("Poppins", 9),
                    anchor="w",
                )
                self.date_weekday_label.pack(anchor="w")
            else:
                weather_top = tk.Frame(tile, bg="#ffffff", bd=0)
                weather_top.pack(anchor="w", fill="x", pady=(3, 1))
                weather_icon = self._load_button_icon(assets_dir / "sunny_clear.svg", 22)
                if weather_icon is not None:
                    self._icon_refs["weather_default"] = weather_icon
                self.weather_icon_label = tk.Label(
                    weather_top,
                    image=weather_icon,
                    bg="#ffffff",
                    bd=0,
                )
                self.weather_icon_label.pack(side="left")
                self.weather_temp_label = tk.Label(
                    weather_top,
                    text="-- " + chr(176) + "C",
                    bg="#ffffff",
                    fg="#183463",
                    font=("Poppins", 14, "bold"),
                    anchor="w",
                )
                self.weather_temp_label.pack(side="left", padx=(8, 0))
                self.weather_desc_label = tk.Label(
                    tile,
                    text="Not available",
                    bg="#ffffff",
                    fg="#51607a",
                    font=("Poppins", 9),
                    anchor="w",
                )
                self.weather_desc_label.pack(anchor="w")

        self.weather_legend_label = tk.Label(
            container,
            text=(
                "Sunny / Clear, Partly Cloudy, Cloudy / Overcast, Rainy, Drizzle, "
                "Thunderstorm, Snow, Fog / Mist, Hazy, Windy, Humid"
            ),
            bg="#f6f8fc",
            fg="#6d788b",
            font=("Poppins", 8),
            anchor="w",
            justify="left",
            wraplength=max(780, w - 80),
        )
        self.weather_legend_label.pack(fill="x", pady=(4, 0))

        self._load_weather_icons(assets_dir)
        self._start_live_tiles()

        footer = ttk.Frame(container, style="Body.TFrame")
        footer.pack(side="bottom", fill="x")

        body = ttk.Frame(container, style="Body.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 8))

        content = ttk.Frame(body, style="Body.TFrame")
        content.pack(fill="both", expand=True)

        chat_shell = tk.Frame(
            content,
            bg="#eef2fb",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
        )
        chat_shell.pack(fill="both", expand=True)
        chat_card = ttk.Frame(chat_shell, style="Card.TFrame", padding=10)
        chat_card.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            chat_card,
            bg="#ffffff",
            fg="#243447",
            insertbackground="#243447",
            borderwidth=0,
            wrap="word",
            font=("Poppins", 11),
            padx=12,
            pady=12,
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(chat_card, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

        self._configure_log_tags(self.log_text)

        self.pending_pdf_frame = tk.Frame(
            footer,
            bg="#f3f6fc",
            highlightthickness=1,
            highlightbackground="#e1e8f4",
            bd=0,
            padx=8,
            pady=6,
        )
        self.pending_pdf_icon_label = tk.Label(
            self.pending_pdf_frame,
            image=self._pdf_card_icon,
            bg="#f3f6fc",
            bd=0,
        )
        self.pending_pdf_icon_label.pack(side="left")
        self.pending_pdf_name_label = tk.Label(
            self.pending_pdf_frame,
            text="",
            bg="#f3f6fc",
            fg="#23408f",
            font=("Poppins", 9, "bold"),
            anchor="w",
        )
        self.pending_pdf_name_label.pack(side="left", padx=(8, 8))
        self.pending_pdf_discard_btn = tk.Button(
            self.pending_pdf_frame,
            text="X",
            command=self._on_pending_pdf_discard,
            bg="#e9eff8",
            fg="#23408f",
            activebackground="#dde7f5",
            relief="flat",
            font=("Poppins", 9, "bold"),
            width=2,
            cursor="hand2",
        )
        self.pending_pdf_discard_btn.pack(side="right")

        self._build_playback_pane(footer)

        tip_shell = tk.Frame(
            footer,
            bg="#f1f5fc",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
            padx=10,
            pady=6,
        )
        tip_shell.pack(fill="x", pady=(0, 6))
        self.tip_label = tk.Label(
            tip_shell,
            text="Tip: Ask naturally, upload a PDF, or use mic. Press Enter to send.",
            bg="#f1f5fc",
            fg="#2b487f",
            font=("Poppins", 9, "bold"),
            anchor="w",
        )
        self.tip_label.pack(side="left", fill="x", expand=True)

        self._build_control_pane(assets_dir)
        self._build_monitor_pane()

        input_shell = tk.Frame(
            footer,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
        )
        input_shell.pack(fill="x")

        input_card = ttk.Frame(input_shell, style="Input.TFrame", padding=12)
        input_card.pack(fill="x")

        self.entry_shell = tk.Frame(
            input_card,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#dbe3f2",
            bd=0,
            padx=8,
            pady=4,
        )
        self.entry_shell.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.input_entry = tk.Entry(
            self.entry_shell,
            bg="#ffffff",
            fg="#1f2d3d",
            insertbackground="#1f2d3d",
            borderwidth=0,
            relief="flat",
            font=("Poppins", 11),
        )
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.input_entry.bind("<Return>", lambda _e: self._on_submit())
        self.input_entry.bind("<KeyPress>", self._on_entry_keypress)
        self.input_entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.input_entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.input_entry.bind("<KeyRelease>", lambda _e: self._refresh_send_state())

        mic_icon = self._load_button_icon(assets_dir / "mic.svg", 24)
        pdf_icon = self._load_button_icon(assets_dir / "pdf.svg", 24)
        send_icon = self._load_button_icon(assets_dir / "send.svg", 24)

        self.mic_btn = tk.Button(
            input_card,
            text="" if mic_icon else "MIC",
            image=mic_icon,
            command=self._on_mic,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            font=("Poppins", 10, "bold"),
            padx=14,
            pady=9,
            cursor="hand2",
        )
        if mic_icon:
            self._icon_refs["mic"] = mic_icon
        self.mic_btn.pack(side="right", padx=(0, 8))
        self._attach_button_hover(self.mic_btn, "#ffffff", "#f4f7ff")

        self.pdf_btn = tk.Button(
            input_card,
            text="" if pdf_icon else "PDF",
            image=pdf_icon,
            command=self._on_pdf,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            font=("Poppins", 10, "bold"),
            padx=14,
            pady=9,
            cursor="hand2",
        )
        if pdf_icon:
            self._icon_refs["pdf"] = pdf_icon
        self.pdf_btn.pack(side="right", padx=(0, 8))
        self._attach_button_hover(self.pdf_btn, "#ffffff", "#f4f7ff")

        self.send_btn = tk.Button(
            input_card,
            text="" if send_icon else "SEND",
            image=send_icon,
            command=self._on_submit,
            bg="#2a5bd7",
            fg="#ffffff",
            activebackground="#1f4ec2",
            relief="flat",
            font=("Poppins", 10, "bold"),
            padx=16,
            pady=9,
            cursor="hand2",
        )
        if send_icon:
            self._icon_refs["send"] = send_icon
        self.send_btn.pack(side="right")
        self._attach_button_hover(self.send_btn, "#2a5bd7", "#1f4ec2")

        self._set_placeholder()
        self.set_mic_muted(False)
        self._set_volume_scale(80)
        self._refresh_send_state()

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

    def _load_rotating_icon_frames(self, icon_path: Path, size_px: int):
        frames = []
        try:
            if icon_path.suffix.lower() == ".svg":
                import cairosvg  # type: ignore

                png_data = cairosvg.svg2png(
                    url=str(icon_path),
                    output_width=size_px,
                    output_height=size_px,
                )
                base = Image.open(io.BytesIO(png_data)).convert("RGBA")
            else:
                base = Image.open(icon_path).convert("RGBA").resize((size_px, size_px), Image.LANCZOS)
            for deg in range(0, 360, 30):
                frames.append(ImageTk.PhotoImage(base.rotate(deg)))
        except Exception:
            pass
        return frames

    def _build_playback_pane(self, parent):
        frame = tk.Frame(
            parent,
            bg="#f3f6fc",
            highlightthickness=1,
            highlightbackground="#d6def0",
            bd=0,
            padx=10,
            pady=8,
        )

        left = tk.Frame(frame, bg="#f3f6fc", bd=0)
        left.pack(side="left", fill="x", expand=True)

        thumb = tk.Label(
            left,
            bg="#dbe4f6",
            width=56,
            height=56,
            bd=0,
        )
        thumb.grid(row=0, column=0, rowspan=3, sticky="w")

        title = tk.Label(
            left,
            text="Now Playing",
            bg="#f3f6fc",
            fg="#183463",
            font=("Poppins", 10, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=1, sticky="w", padx=(10, 0))

        artist = tk.Label(
            left,
            text="",
            bg="#f3f6fc",
            fg="#546684",
            font=("Poppins", 9),
            anchor="w",
        )
        artist.grid(row=1, column=1, sticky="w", padx=(10, 0))

        progress = ttk.Progressbar(
            left,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=0,
        )
        progress.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
        left.grid_columnconfigure(1, weight=1)

        right = tk.Frame(frame, bg="#f3f6fc", bd=0)
        right.pack(side="right", padx=(10, 0))

        prev_icon = self._load_button_icon(Path(self._assets_dir) / "previous.svg", 18)
        play_icon = self._load_button_icon(Path(self._assets_dir) / "play.svg", 18)
        pause_icon = self._load_button_icon(Path(self._assets_dir) / "pause.svg", 18)
        next_icon = self._load_button_icon(Path(self._assets_dir) / "next.svg", 18)
        if prev_icon is not None:
            self._icon_refs["playback_prev"] = prev_icon
        if play_icon is not None:
            self._icon_refs["playback_play"] = play_icon
        if pause_icon is not None:
            self._icon_refs["playback_pause"] = pause_icon
        if next_icon is not None:
            self._icon_refs["playback_next"] = next_icon

        btn_prev = tk.Button(
            right,
            text="" if prev_icon else "Prev",
            image=prev_icon,
            command=lambda: self._on_playback_control("previous"),
            bg="#f3f6fc",
            fg="#23408f",
            activebackground="#eaf0fb",
            relief="flat",
            bd=0,
            padx=8,
            pady=7,
            cursor="hand2",
        )
        btn_prev.pack(side="left", padx=(0, 6))
        self._attach_button_hover(btn_prev, "#f3f6fc", "#eaf0fb")

        btn_toggle = tk.Button(
            right,
            text="" if pause_icon else "Pause",
            image=pause_icon,
            command=lambda: self._on_playback_control("toggle"),
            bg="#f3f6fc",
            fg="#23408f",
            activebackground="#eaf0fb",
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
        )
        btn_toggle.pack(side="left", padx=(0, 6))
        self._attach_button_hover(btn_toggle, "#f3f6fc", "#eaf0fb")

        btn_next = tk.Button(
            right,
            text="" if next_icon else "Next",
            image=next_icon,
            command=lambda: self._on_playback_control("next"),
            bg="#f3f6fc",
            fg="#23408f",
            activebackground="#eaf0fb",
            relief="flat",
            bd=0,
            padx=8,
            pady=7,
            cursor="hand2",
        )
        btn_next.pack(side="left")
        self._attach_button_hover(btn_next, "#f3f6fc", "#eaf0fb")

        time_lbl = tk.Label(
            frame,
            text="00:00 / 00:00",
            bg="#f3f6fc",
            fg="#546684",
            font=("Poppins", 8),
        )
        time_lbl.place(relx=1.0, rely=1.0, x=-8, y=-4, anchor="se")

        self._playback_frame = frame
        self._playback_thumb_label = thumb
        self._playback_title_label = title
        self._playback_artist_label = artist
        self._playback_progress = progress
        self._playback_time_label = time_lbl
        self._playback_btn_prev = btn_prev
        self._playback_btn_toggle = btn_toggle
        self._playback_btn_next = btn_next

    def _seconds_to_mmss(self, value: float) -> str:
        total = max(0, int(value))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _load_playback_thumbnail(self, thumb_url: str):
        if not thumb_url or thumb_url == self._playback_last_thumb_url:
            return
        self._playback_last_thumb_url = thumb_url
        try:
            with urlopen(thumb_url, timeout=3) as resp:
                raw = resp.read()
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img = img.resize((56, 56), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._playback_thumb_image = photo
            if self._playback_thumb_label is not None:
                self._playback_thumb_label.configure(image=photo, text="")
        except Exception:
            pass

    def _on_playback_control(self, action: str):
        if self._playback_control_handler is None:
            return
        self._playback_control_handler(action)

    def _show_playback_pane(self):
        if self._playback_frame is None or self._playback_visible:
            return
        self._playback_frame.pack(fill="x", pady=(0, 6))
        self._playback_visible = True

    def _hide_playback_pane(self):
        if self._playback_frame is None or not self._playback_visible:
            return
        self._playback_frame.pack_forget()
        self._playback_visible = False
        self._playback_last_thumb_url = ""
        self._playback_thumb_image = None
        if self._playback_thumb_label is not None:
            self._playback_thumb_label.configure(image="", text="")

    def _refresh_playback_pane(self):
        if self._playback_state_handler is None:
            self._playback_poll_job = self.root.after(900, self._refresh_playback_pane)
            return
        try:
            state = self._playback_state_handler() or {}
        except Exception:
            state = {}
        active = bool(state.get("active"))
        if not active:
            self._hide_playback_pane()
            self._playback_poll_job = self.root.after(900, self._refresh_playback_pane)
            return

        self._show_playback_pane()
        title = str(state.get("title") or "Now Playing")
        artist = str(state.get("artist") or "Unknown Artist")
        paused = bool(state.get("paused"))
        pos = float(state.get("position_sec") or 0.0)
        dur = float(state.get("duration_sec") or 0.0)
        pct = float(state.get("progress_pct") or 0.0)
        thumb_url = str(state.get("thumbnail") or "")

        if self._playback_title_label is not None:
            self._playback_title_label.configure(text=title[:52] + ("..." if len(title) > 52 else ""))
        if self._playback_artist_label is not None:
            self._playback_artist_label.configure(text=artist[:52] + ("..." if len(artist) > 52 else ""))
        if self._playback_progress is not None:
            self._playback_progress.configure(value=max(0.0, min(100.0, pct)))
        if self._playback_time_label is not None:
            if dur > 0:
                self._playback_time_label.configure(
                    text=f"{self._seconds_to_mmss(pos)} / {self._seconds_to_mmss(dur)}"
                )
            else:
                self._playback_time_label.configure(text=f"{self._seconds_to_mmss(pos)} / --:--")
        if self._playback_btn_toggle is not None:
            icon = self._icon_refs.get("playback_play") if paused else self._icon_refs.get("playback_pause")
            if icon is not None:
                self._playback_btn_toggle.configure(image=icon, text="")
            else:
                self._playback_btn_toggle.configure(text=("Play" if paused else "Pause"))
        if thumb_url:
            self._load_playback_thumbnail(thumb_url)
        elif self._playback_thumb_label is not None:
            self._playback_thumb_label.configure(image="", text="")
            self._playback_thumb_image = None
            self._playback_last_thumb_url = ""

        self._playback_poll_job = self.root.after(700, self._refresh_playback_pane)

    def _build_control_pane(self, assets_dir: Path):
        pane = tk.Toplevel(self.root)
        pane.title("Controls")
        pane.configure(bg="#f8fafc")
        pane.resizable(False, False)
        pane.transient(self.root)
        pane.withdraw()
        pane.protocol("WM_DELETE_WINDOW", self._hide_control_pane)

        shell = tk.Frame(
            pane,
            bg="#f8fafc",
            padx=12,
            pady=12,
            bd=0,
        )
        shell.pack(fill="both", expand=True)

        mic_panel = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#dbe3ee",
            bd=0,
            padx=10,
            pady=8,
        )
        mic_panel.pack(fill="x")

        tk.Label(
            mic_panel,
            text="Microphone",
            bg="#ffffff",
            fg="#415373",
            font=("Poppins", 9, "bold"),
        ).pack(anchor="w")
        self.mic_state_label = tk.Label(
            mic_panel,
            text="Status: Unmuted",
            bg="#ffffff",
            fg="#1f7a45",
            font=("Poppins", 9),
        )
        self.mic_state_label.pack(anchor="w", pady=(2, 0))

        mute_icon = self._load_button_icon(assets_dir / "mute.svg", 18)
        mic_on_icon = self._load_button_icon(assets_dir / "mic.svg", 18)
        if mute_icon:
            self._icon_refs["mute"] = mute_icon
        if mic_on_icon:
            self._icon_refs["mic_small"] = mic_on_icon
        self.mic_mute_btn = tk.Button(
            mic_panel,
            text="Mute Mic",
            image=mute_icon,
            compound="left",
            command=self._on_mic_mute_toggle,
            bg="#ffffff",
            fg="#8a1f1f",
            activebackground="#f7ecea",
            relief="flat",
            font=("Poppins", 9, "bold"),
            padx=10,
            pady=5,
            cursor="hand2",
        )
        self.mic_mute_btn.pack(anchor="w", pady=(6, 0))
        self._attach_button_hover(self.mic_mute_btn, "#ffffff", "#f7ecea")

        volume_panel = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#dbe3ee",
            bd=0,
            padx=10,
            pady=8,
        )
        volume_panel.pack(fill="x", pady=(8, 0))

        volume_mute_icon = self._load_button_icon(assets_dir / "volume_mute.svg", 18)
        volume_low_icon = self._load_button_icon(assets_dir / "volume_low.svg", 18)
        volume_high_icon = self._load_button_icon(assets_dir / "volume_high.svg", 18)
        if volume_mute_icon:
            self._icon_refs["volume_mute"] = volume_mute_icon
        if volume_low_icon:
            self._icon_refs["volume_low"] = volume_low_icon
        if volume_high_icon:
            self._icon_refs["volume_high"] = volume_high_icon

        tk.Label(
            volume_panel,
            text="Voice Volume",
            bg="#ffffff",
            fg="#425679",
            font=("Poppins", 9, "bold"),
        ).pack(side="left", padx=(0, 10))

        self.volume_mute_btn = tk.Button(
            volume_panel,
            text="Mute",
            image=volume_mute_icon,
            compound="left",
            bg="#ffffff",
            activebackground="#f4f7ff",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: self._set_volume_scale(0),
        )
        self.volume_mute_btn.pack(side="left", padx=(0, 6))

        tk.Label(
            volume_panel,
            text="Low",
            image=volume_low_icon,
            compound="left",
            bg="#ffffff",
            bd=0,
            fg="#4f6080",
            font=("Poppins", 8),
        ).pack(side="left")
        self.volume_scale = tk.Scale(
            volume_panel,
            from_=0,
            to=100,
            orient="horizontal",
            length=180,
            showvalue=0,
            bd=0,
            highlightthickness=0,
            bg="#ffffff",
            troughcolor="#d8e4ff",
            activebackground="#2a5bd7",
            command=self._on_volume_changed,
        )
        self.volume_scale.pack(side="left", padx=(6, 6))
        tk.Label(
            volume_panel,
            text="High",
            image=volume_high_icon,
            compound="left",
            bg="#ffffff",
            bd=0,
            fg="#4f6080",
            font=("Poppins", 8),
        ).pack(side="left", padx=(0, 6))
        self.volume_value_label = tk.Label(
            volume_panel,
            text="100%",
            bg="#ffffff",
            fg="#425679",
            font=("Poppins", 9, "bold"),
        )
        self.volume_value_label.pack(side="left")

        window_panel = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#dbe3ee",
            bd=0,
            padx=10,
            pady=8,
        )
        window_panel.pack(fill="x", pady=(8, 0))
        tk.Label(
            window_panel,
            text="Window",
            bg="#ffffff",
            fg="#425679",
            font=("Poppins", 9, "bold"),
        ).pack(anchor="w")
        self.always_on_top_chk = tk.Checkbutton(
            window_panel,
            text="Always On Top (show compact window on minimize)",
            variable=self._always_on_top_var,
            onvalue=True,
            offvalue=False,
            command=self._on_always_on_top_toggled,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#ffffff",
            font=("Poppins", 9),
            anchor="w",
            justify="left",
        )
        self.always_on_top_chk.pack(anchor="w", pady=(6, 0))

        self._control_pane = pane

    def _toggle_control_pane(self):
        if self._control_pane is None:
            return
        if str(self._control_pane.state()) == "withdrawn":
            self._show_control_pane()
        else:
            self._hide_control_pane()

    def _show_control_pane(self):
        if self._control_pane is None:
            return
        self._control_pane.deiconify()
        self._control_pane.lift()
        self._control_pane.focus_force()
        if hasattr(self, "settings_btn"):
            self.settings_btn.configure(bg="#f0f4fb", activebackground="#e7eef9")

    def _hide_control_pane(self):
        if self._control_pane is None:
            return
        self._control_pane.withdraw()
        if hasattr(self, "settings_btn"):
            self.settings_btn.configure(bg="#ffffff", activebackground="#f4f7ff")

    def _on_always_on_top_toggled(self):
        self.set_always_on_top(bool(self._always_on_top_var.get()))

    def set_always_on_top(self, enabled: bool):
        self._always_on_top_enabled = bool(enabled)
        self._always_on_top_var.set(self._always_on_top_enabled)
        # Keep main window normal; only compact minimized window should be topmost.
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass
        if not self._always_on_top_enabled:
            self._hide_compact_window()
        elif self.root.state() == "iconic":
            self.root.after(60, self._show_compact_window)

    def _on_root_unmap(self, _event=None):
        if self._suppress_unmap_handler:
            return
        if not self._always_on_top_enabled:
            return
        try:
            if self.root.state() == "iconic":
                self.root.after(60, self._show_compact_window)
        except Exception:
            pass

    def _on_root_map(self, _event=None):
        if self._suppress_unmap_handler:
            return
        self._hide_compact_window()

    def _show_compact_window(self):
        if not self._always_on_top_enabled:
            return
        if self._mini_window is None:
            self._build_compact_window()
        if self._mini_window is None:
            return
        sw = self.root.winfo_screenwidth()
        x = max(10, sw - 460 - 18)
        y = 18
        self._mini_window.geometry(f"460x420+{x}+{y}")
        self._sync_compact_log_from_main()
        self._mini_window.deiconify()
        self._mini_window.lift()
        try:
            self._mini_window.attributes("-topmost", True)
        except Exception:
            pass
        if self.root.state() == "iconic":
            self._suppress_unmap_handler = True
            try:
                self.root.withdraw()
            finally:
                self._suppress_unmap_handler = False

    def _hide_compact_window(self):
        if self._mini_window is None:
            return
        try:
            self._mini_window.withdraw()
        except Exception:
            pass

    def _restore_from_compact(self):
        self._hide_compact_window()
        self._suppress_unmap_handler = True
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", False)
            self.root.focus_force()
        finally:
            self._suppress_unmap_handler = False

    def _build_compact_window(self):
        mini = tk.Toplevel(self.root)
        mini.title("SPARKY")
        mini.configure(bg="#f8fafc")
        mini.resizable(False, False)
        mini.minsize(440, 380)
        mini.withdraw()
        mini.protocol("WM_DELETE_WINDOW", self._restore_from_compact)

        shell = tk.Frame(mini, bg="#f8fafc", padx=10, pady=10, bd=0)
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=0)
        shell.grid_rowconfigure(1, weight=1)
        shell.grid_rowconfigure(2, weight=0)
        shell.grid_columnconfigure(0, weight=1)

        header = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#dbe3ee",
            bd=0,
            padx=10,
            pady=8,
        )
        header.grid(row=0, column=0, sticky="ew")
        text_logo = None
        if hasattr(self, "_assets_dir"):
            text_logo = self._load_title_image(Path(self._assets_dir) / "text.png", max_w=170, max_h=24)
        if text_logo is not None:
            name_lbl = tk.Label(header, image=text_logo, bg="#ffffff", bd=0)
            name_lbl.image = text_logo
            self._icon_refs["mini_text_logo"] = text_logo
        else:
            name_lbl = tk.Label(
                header,
                text=SYSTEM_NAME,
                bg="#ffffff",
                fg="#1e2a3a",
                font=("Poppins", 11, "bold"),
            )
        name_lbl.pack(side="left")
        name_lbl.bind("<Double-Button-1>", lambda _e: self._restore_from_compact())
        self._mini_status_label = tk.Label(
            header,
            text="Online",
            bg=self._status_palette["online"],
            fg="#2c8a3d",
            font=("Poppins", 9, "bold"),
            padx=8,
            pady=4,
            bd=0,
        )
        self._mini_status_label.pack(side="right")

        chat_shell = tk.Frame(
            shell,
            bg="#eef2fb",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
        )
        chat_shell.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        chat_card = tk.Frame(chat_shell, bg="#ffffff", bd=0, padx=8, pady=8)
        chat_card.pack(fill="both", expand=True)

        mini_log = tk.Text(
            chat_card,
            bg="#ffffff",
            fg="#243447",
            insertbackground="#243447",
            borderwidth=0,
            wrap="word",
            font=("Poppins", 10),
            padx=8,
            pady=8,
        )
        mini_log.pack(side="left", fill="both", expand=True)
        mini_scroll = ttk.Scrollbar(chat_card, orient="vertical", command=mini_log.yview)
        mini_scroll.pack(side="right", fill="y")
        mini_log.configure(yscrollcommand=mini_scroll.set, state="disabled")
        self._configure_log_tags(mini_log)

        input_shell = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e8f5",
            bd=0,
            padx=8,
            pady=8,
        )
        input_shell.grid(row=2, column=0, sticky="ew")
        mini_entry = tk.Entry(
            input_shell,
            bg="#ffffff",
            fg="#1f2d3d",
            insertbackground="#1f2d3d",
            borderwidth=0,
            relief="flat",
            font=("Poppins", 10),
        )
        mini_entry.pack(side="left", fill="x", expand=True, ipady=6)
        mini_mic_icon = self._icon_refs.get("mic") or self._load_button_icon(Path(self._assets_dir) / "mic.svg", 18)
        mini_pdf_icon = self._icon_refs.get("pdf") or self._load_button_icon(Path(self._assets_dir) / "pdf.svg", 18)
        mini_send_icon = self._icon_refs.get("send") or self._load_button_icon(Path(self._assets_dir) / "send.svg", 18)
        if mini_mic_icon is not None:
            self._icon_refs["mini_mic"] = mini_mic_icon
        if mini_pdf_icon is not None:
            self._icon_refs["mini_pdf"] = mini_pdf_icon
        if mini_send_icon is not None:
            self._icon_refs["mini_send"] = mini_send_icon

        mini_mic = tk.Button(
            input_shell,
            text="" if mini_mic_icon else "MIC",
            image=mini_mic_icon,
            command=self._on_mic,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            font=("Poppins", 8, "bold"),
            padx=8,
            pady=6,
            cursor="hand2",
        )
        mini_mic.pack(side="right", padx=(6, 0))

        mini_pdf = tk.Button(
            input_shell,
            text="" if mini_pdf_icon else "PDF",
            image=mini_pdf_icon,
            command=self._on_pdf,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            font=("Poppins", 8, "bold"),
            padx=8,
            pady=6,
            cursor="hand2",
        )
        mini_pdf.pack(side="right", padx=(6, 0))

        mini_send = tk.Button(
            input_shell,
            text="" if mini_send_icon else "SEND",
            image=mini_send_icon,
            command=self._on_mini_submit,
            bg="#2a5bd7",
            fg="#ffffff",
            activebackground="#1f4ec2",
            relief="flat",
            font=("Poppins", 9, "bold"),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        mini_send.pack(side="right", padx=(8, 0))
        mini_entry.bind("<Return>", lambda _e: self._on_mini_submit())

        self._mini_window = mini
        self._mini_log_text = mini_log
        self._mini_input_entry = mini_entry
        self._sync_compact_log_from_main(force=True)

    def _sync_compact_log_from_main(self, force: bool = False):
        if self._mini_log_text is None:
            return
        try:
            current = self._mini_log_text.get("1.0", tk.END).strip()
            if current and not force:
                return
            source = self.log_text.get("1.0", tk.END)
            self._mini_log_text.configure(state="normal")
            self._mini_log_text.delete("1.0", tk.END)
            self._mini_log_text.insert(tk.END, source)
            self._mini_log_text.see(tk.END)
            self._mini_log_text.configure(state="disabled")
        except Exception:
            pass

    def _on_mini_submit(self):
        if self._submit_handler is None or self._mini_input_entry is None:
            return
        text = self._mini_input_entry.get().strip()
        if not text:
            return
        self._mini_input_entry.delete(0, tk.END)
        self._submit_handler(text)

    def _on_main_close(self):
        if self._playback_poll_job is not None:
            try:
                self.root.after_cancel(self._playback_poll_job)
            except Exception:
                pass
            self._playback_poll_job = None
        for win in (self._mini_window, self._control_pane, self._monitor_pane, self._update_window):
            try:
                if win is not None:
                    win.destroy()
            except Exception:
                pass
        self.root.destroy()

    def _build_monitor_pane(self):
        pane = tk.Toplevel(self.root)
        pane.title("System Resource Monitor")
        pane.configure(bg="#f8fafc")
        pane.resizable(False, False)
        pane.transient(self.root)
        pane.withdraw()
        pane.protocol("WM_DELETE_WINDOW", self._hide_monitor_pane)

        shell = tk.Frame(pane, bg="#f8fafc", padx=12, pady=12, bd=0)
        shell.pack(fill="both", expand=True)

        labels = {}
        rows = [
            ("CPU Temperature", "cpu_temp"),
            ("GPU Usage", "gpu_usage"),
            ("CPU Usage", "cpu_usage"),
            ("RAM Usage", "ram_usage"),
            ("Storage Usage", "storage_usage"),
            ("Upload Speed", "upload"),
            ("Download Speed", "download"),
        ]
        for title, key in rows:
            row = tk.Frame(
                shell,
                bg="#ffffff",
                highlightthickness=1,
                highlightbackground="#dbe3ee",
                bd=0,
                padx=10,
                pady=8,
            )
            row.pack(fill="x", pady=(0, 8))
            tk.Label(
                row,
                text=title,
                bg="#ffffff",
                fg="#425679",
                font=("Poppins", 9, "bold"),
                anchor="w",
            ).pack(side="left")
            value = tk.Label(
                row,
                text="--",
                bg="#ffffff",
                fg="#0f172a",
                font=("Poppins", 9),
                anchor="e",
            )
            value.pack(side="right")
            labels[key] = value

        self.speed_test_btn = tk.Button(
            shell,
            text="Run Speed Test",
            command=self._on_speed_test_clicked,
            bg="#ffffff",
            fg="#23408f",
            activebackground="#f4f7ff",
            relief="flat",
            bd=0,
            font=("Poppins", 9, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        self.speed_test_btn.pack(anchor="e")
        self._attach_button_hover(self.speed_test_btn, "#ffffff", "#f4f7ff")

        self._monitor_pane = pane
        self._monitor_labels = labels
        self._net_snapshot = None

    def _toggle_monitor_pane(self):
        if self._monitor_pane is None:
            return
        if str(self._monitor_pane.state()) == "withdrawn":
            self._show_monitor_pane()
        else:
            self._hide_monitor_pane()

    def _show_monitor_pane(self):
        if self._monitor_pane is None:
            return
        self._monitor_pane.deiconify()
        self._monitor_pane.lift()
        self._monitor_pane.focus_force()
        if hasattr(self, "monitor_btn"):
            self.monitor_btn.configure(bg="#f0f4fb", activebackground="#e7eef9")
        self._start_speed_test_async()
        self._update_monitor_pane()

    def _hide_monitor_pane(self):
        if self._monitor_pane is None:
            return
        self._monitor_pane.withdraw()
        if hasattr(self, "monitor_btn"):
            self.monitor_btn.configure(bg="#ffffff", activebackground="#f4f7ff")
        if self._monitor_job is not None:
            try:
                self.root.after_cancel(self._monitor_job)
            except Exception:
                pass
            self._monitor_job = None

    def get_system_resource_snapshot(self):
        stats, snap = collect_system_stats(self._net_snapshot, speed_test=self._speed_test_result)
        self._net_snapshot = snap
        return stats

    def get_system_resource_report(self):
        now = time.time()
        if (self._speed_test_result is None) or (now - self._speed_test_ts > 180):
            down, up = internet_speed_test_mbps(timeout_sec=8, down_bytes=5_000_000, up_bytes=1_000_000)
            self._speed_test_result = (down, up)
            self._speed_test_ts = time.time()
        stats = self.get_system_resource_snapshot()
        return format_system_stats_report(stats, include_suggestions=True)

    def run_speed_test_report(self):
        down, up = internet_speed_test_mbps(timeout_sec=12, down_bytes=8_000_000, up_bytes=1_500_000)
        self._speed_test_result = (down, up)
        self._speed_test_ts = time.time()
        stats = self.get_system_resource_snapshot()
        return format_system_stats_report(stats, include_suggestions=True)

    def _update_monitor_pane(self):
        if self._monitor_pane is None or str(self._monitor_pane.state()) == "withdrawn":
            return
        if (self._speed_test_result is None or (time.time() - self._speed_test_ts > 180)) and not self._speed_test_inflight:
            self._start_speed_test_async()
        stats = self.get_system_resource_snapshot()

        def pct(v):
            return "N/A" if v is None else f"{float(v):.1f}%"

        def mbps(v):
            if v is None:
                return "Testing..." if self._speed_test_inflight else "Unavailable"
            vv = float(v)
            return f"{(vv / 8.0):.2f} MB/s"

        cpu_temp = stats.get("cpu_temp_c")
        self._monitor_labels["cpu_temp"].configure(
            text=("Not available" if cpu_temp is None else f"{float(cpu_temp):.1f} C")
        )
        self._monitor_labels["gpu_usage"].configure(text=pct(stats.get("gpu_usage_percent")))
        self._monitor_labels["cpu_usage"].configure(text=pct(stats.get("cpu_usage_percent")))
        self._monitor_labels["ram_usage"].configure(text=pct(stats.get("ram_usage_percent")))
        self._monitor_labels["storage_usage"].configure(text=pct(stats.get("storage_usage_percent")))
        self._monitor_labels["upload"].configure(text=mbps(stats.get("upload_mbps")))
        self._monitor_labels["download"].configure(text=mbps(stats.get("download_mbps")))

        self._monitor_job = self.root.after(1000, self._update_monitor_pane)

    def _on_speed_test_clicked(self):
        self._start_speed_test_async(force=True)

    def _start_speed_test_async(self, force: bool = False):
        if self._speed_test_inflight:
            return
        if force:
            self._speed_test_result = None
            self._speed_test_ts = 0.0
            if hasattr(self, "speed_test_btn"):
                self.speed_test_btn.configure(text="Testing...", state=tk.DISABLED)
        self._speed_test_inflight = True

        def _worker():
            down, up = internet_speed_test_mbps(timeout_sec=10, down_bytes=8_000_000, up_bytes=1_500_000)

            def _apply():
                self._speed_test_result = (down, up)
                self._speed_test_ts = time.time()
                self._speed_test_inflight = False
                if hasattr(self, "speed_test_btn"):
                    self.speed_test_btn.configure(text="Run Speed Test", state=tk.NORMAL)

            self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _load_weather_icons(self, assets_dir: Path):
        mapping = {
            "Sunny / Clear": "sunny_clear.svg",
            "Partly Cloudy": "partly_cloudy.svg",
            "Cloudy / Overcast": "cloudy.svg",
            "Rainy": "rainy.svg",
            "Drizzle": "drizzle.svg",
            "Thunderstorm": "thunderstorm.svg",
            "Snow": "snow.svg",
            "Fog / Mist": "fog.svg",
            "Hazy": "hazy.svg",
            "Windy": "windy.svg",
            "Humid": "humid.svg",
        }
        icons = {}
        for label, filename in mapping.items():
            img = self._load_button_icon(assets_dir / filename, 22)
            if img is not None:
                icons[label] = img
                self._icon_refs[f"weather_{label}"] = img
        self._weather_icons = icons

    def _start_live_tiles(self):
        self._refresh_clock_tile()
        self._refresh_weather_tile()

    def _refresh_clock_tile(self):
        now = datetime.now().astimezone()
        self.time_value_label.configure(text=now.strftime("%I:%M:%S %p"))
        self.time_tz_label.configure(text=f"{now.tzname() or 'Local Time'} (Auto)")
        self.date_value_label.configure(text=now.strftime("%d %b %Y"))
        self.date_weekday_label.configure(text=now.strftime("%A"))
        self._clock_job = self.root.after(1000, self._refresh_clock_tile)

    def _refresh_weather_tile(self):
        def _worker():
            data = self._fetch_weather_data()
            self.root.after(0, self._apply_weather_data, data)

        threading.Thread(target=_worker, daemon=True).start()
        self._weather_job = self.root.after(600000, self._refresh_weather_tile)

    def _apply_weather_data(self, data: dict):
        temp = data.get("temp")
        cond = data.get("condition") or "Not available"
        icon_key = data.get("icon")
        if temp is None:
            self.weather_temp_label.configure(text="-- " + chr(176) + "C")
        else:
            self.weather_temp_label.configure(text=f"{temp:.1f} {chr(176)}C")
        self.weather_desc_label.configure(text=cond)
        img = self._weather_icons.get(icon_key)
        if img is not None:
            self.weather_icon_label.configure(image=img)

    def _fetch_weather_data(self) -> dict:
        try:
            def _fetch_json(url: str, params: dict | None = None, timeout: int = 6) -> dict | None:
                query_url = url
                if params:
                    query_url = f"{url}?{urlencode(params)}"
                try:
                    with urlopen(query_url, timeout=timeout) as resp:
                        if getattr(resp, "status", 200) != 200:
                            return None
                        return json.loads(resp.read().decode("utf-8", errors="ignore"))
                except Exception:
                    return None

            city = ""
            for url in ("https://ipapi.co/json/", "https://ipinfo.io/json"):
                payload = _fetch_json(url, timeout=4)
                if payload:
                    city = (payload.get("city") or "").strip()
                    if city:
                        break
            if not city:
                return {"temp": None, "condition": "Not available", "icon": None}

            geo = _fetch_json(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": city, "count": 1, "language": "en", "format": "json"},
                timeout=6,
            )
            if not geo:
                return {"temp": None, "condition": "Not available", "icon": None}
            results = (geo or {}).get("results") or []
            if not results:
                return {"temp": None, "condition": "Not available", "icon": None}
            lat = float(results[0].get("latitude"))
            lon = float(results[0].get("longitude"))

            wx = _fetch_json(
                "https://api.open-meteo.com/v1/forecast",
                {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                },
                timeout=8,
            )
            if not wx:
                return {"temp": None, "condition": "Not available", "icon": None}
            current = (wx or {}).get("current") or {}
            temp = current.get("temperature_2m")
            code = current.get("weather_code")
            humidity = current.get("relative_humidity_2m")
            wind = current.get("wind_speed_10m")
            cond = self._map_weather_condition(code, humidity, wind)
            return {
                "temp": float(temp) if temp is not None else None,
                "condition": cond,
                "icon": cond,
            }
        except Exception:
            return {"temp": None, "condition": "Not available", "icon": None}

    def _map_weather_condition(self, code, humidity, wind) -> str:
        try:
            c = int(code)
        except Exception:
            c = -1

        if c in {0, 1}:
            base = "Sunny / Clear"
        elif c == 2:
            base = "Partly Cloudy"
        elif c == 3:
            base = "Cloudy / Overcast"
        elif c in {45, 48}:
            base = "Fog / Mist"
        elif c in {51, 53, 55, 56, 57}:
            base = "Drizzle"
        elif c in {61, 63, 65, 66, 67, 80, 81, 82}:
            base = "Rainy"
        elif c in {71, 73, 75, 77, 85, 86}:
            base = "Snow"
        elif c in {95, 96, 99}:
            base = "Thunderstorm"
        else:
            base = "Cloudy / Overcast"

        try:
            if wind is not None and float(wind) >= 30:
                return "Windy"
        except Exception:
            pass

        try:
            if humidity is not None and float(humidity) >= 88:
                return "Humid"
            if humidity is not None and float(humidity) >= 74 and base in {"Sunny / Clear", "Partly Cloudy"}:
                return "Hazy"
        except Exception:
            pass

        return base
    def _attach_button_hover(self, btn: tk.Button, normal: str, hover: str):
        def _enter(_e):
            if str(btn.cget("state")) != "disabled":
                btn.configure(bg=hover)

        def _leave(_e):
            if str(btn.cget("state")) != "disabled":
                btn.configure(bg=normal)

        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)

    def _configure_log_tags(self, widget: tk.Text):
        widget.tag_config("you", foreground="#1f4aa8", font=("Poppins", 11, "bold"))
        widget.tag_config("ai", foreground="#1d7a4a", font=("Poppins", 11, "bold"))
        widget.tag_config("sys", foreground="#7a5a10", font=("Poppins", 10, "italic"))
        widget.tag_config("body_you", foreground="#1a2f59", font=("Poppins", 11))
        widget.tag_config("body_ai", foreground="#163d2d", font=("Poppins", 11))
        widget.tag_config("body_sys", foreground="#4d3d15", font=("Poppins", 10))
        widget.tag_config("body_ai_bold", foreground="#163d2d", font=("Poppins", 11, "bold"))
        widget.tag_config(
            "body_ai_bullet",
            foreground="#163d2d",
            font=("Poppins", 11),
            lmargin1=18,
            lmargin2=34,
        )
        widget.tag_config("gap", spacing1=2, spacing3=8)

    def _set_status(self, text: str, color: str, keep_icon: bool = False):
        low = (text or "").strip().lower()
        if "listen" in low:
            bg = self._status_palette["listening"]
        elif "respond" in low:
            bg = self._status_palette["responding"]
        elif "process" in low:
            bg = self._status_palette["processing"]
        else:
            bg = self._status_palette["online"]
        if keep_icon:
            self.status_label.configure(text=text, fg=color, bg=bg)
        else:
            self.status_label.configure(text=text, fg=color, bg=bg, image="")
        if self._mini_status_label is not None:
            self._mini_status_label.configure(text=text, fg=color, bg=bg)

    def write_log(self, text: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.write_log, text)
            return

        raw = (text or "").strip()
        if not raw:
            return

        if raw.lower().startswith("you:"):
            role_tag = "you"
            body_tag = "body_you"
            body = raw[4:].strip()
            role = "You"
        elif raw.lower().startswith("ai:"):
            role_tag = "ai"
            body_tag = "body_ai"
            body = raw[3:].strip()
            role = "Sparky"
        else:
            role_tag = "sys"
            body_tag = "body_sys"
            body = raw[4:].strip() if raw.lower().startswith("sys:") else raw
            role = "System"

        stamp = time.strftime("%H:%M")
        line_header = f"[{stamp}] {role}: "

        self._append_log_to_widget(self.log_text, line_header, role_tag, body_tag, body)
        if self._mini_log_text is not None:
            self._append_log_to_widget(self._mini_log_text, line_header, role_tag, body_tag, body)

    def _append_log_to_widget(self, widget: tk.Text, line_header: str, role_tag: str, body_tag: str, body: str):
        widget.configure(state="normal")
        widget.insert(tk.END, line_header, role_tag)
        if role_tag == "ai":
            self._insert_markdown_body(widget, body)
            widget.insert(tk.END, "\n", "gap")
        else:
            widget.insert(tk.END, f"{body}\n\n", (body_tag, "gap"))
        widget.see(tk.END)
        widget.configure(state="disabled")

    def _insert_markdown_body(self, widget: tk.Text, text: str):
        lines = (text or "").splitlines() or [""]
        bold_re = re.compile(r"\*\*(.+?)\*\*")

        def _insert_with_bold(raw_line: str):
            pos = 0
            for m in bold_re.finditer(raw_line):
                if m.start() > pos:
                    widget.insert(tk.END, raw_line[pos:m.start()], "body_ai")
                widget.insert(tk.END, m.group(1), "body_ai_bold")
                pos = m.end()
            if pos < len(raw_line):
                widget.insert(tk.END, raw_line[pos:], "body_ai")

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("* ") or stripped.startswith("- "):
                widget.insert(tk.END, "\u2022 ", "body_ai_bullet")
                _insert_with_bold(stripped[2:])
            else:
                _insert_with_bold(line)
            widget.insert(tk.END, "\n", "body_ai")

    def add_pdf_chat_card(self, pdf_path: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.add_pdf_chat_card, pdf_path)
            return
        name = Path(pdf_path).name
        self.log_text.configure(state="normal")
        card = tk.Frame(
            self.log_text,
            bg="#eef3ff",
            highlightthickness=1,
            highlightbackground="#c7d5f6",
            bd=0,
            padx=10,
            pady=8,
        )
        icon_lbl = tk.Label(card, image=self._pdf_card_icon, bg="#eef3ff", bd=0)
        icon_lbl.pack(side="left")
        name_lbl = tk.Label(
            card,
            text=name,
            bg="#eef3ff",
            fg="#23408f",
            font=("Poppins", 10, "bold"),
            anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 0))
        self.log_text.window_create(tk.END, window=card)
        self.log_text.insert(tk.END, "\n\n", "gap")
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
        self._set_status("Listening", "#1f4ec2")
        if self._listen_timeout_job is not None:
            try:
                self.root.after_cancel(self._listen_timeout_job)
            except Exception:
                pass
        # Safety net: never stay in listening state indefinitely.
        self._listen_timeout_job = self.root.after(6500, self.stop_listening)

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
        self._set_status("Online", "#2c8a3d")

    def update_listening_level(self, level: float):
        return

    def start_processing(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.start_processing)
            return
        if self._processing:
            return
        self._processing = True
        self._loading_frame_idx = 0
        self._animate_processing_icon()

    def stop_processing(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.stop_processing)
            return
        self._processing = False
        if self._processing_job is not None:
            try:
                self.root.after_cancel(self._processing_job)
            except Exception:
                pass
            self._processing_job = None
        if self._listening:
            self._set_status("Listening", "#1f4ec2")
        elif getattr(self, "speaking", False):
            self._set_status("Responding", "#a36b00")
        else:
            self._set_status("Online", "#2c8a3d")

    def _animate_processing_icon(self):
        if not self._processing:
            return
        if self._loading_frames:
            self._loading_frame_idx = (self._loading_frame_idx + 1) % len(self._loading_frames)
            self.status_label.configure(
                text="Processing",
                fg="#2a5bd7",
                bg=self._status_palette["processing"],
                image=self._loading_frames[self._loading_frame_idx],
            )
        else:
            self._set_status("Processing", "#2a5bd7")
        self._processing_job = self.root.after(80, self._animate_processing_icon)

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

    def set_mic_mute_toggle_handler(self, fn):
        self._mic_mute_toggle_handler = fn

    def set_tts_volume_handler(self, fn):
        self._tts_volume_handler = fn

    def set_pdf_handler(self, fn):
        self._pdf_handler = fn

    def set_pdf_discard_handler(self, fn):
        self._pdf_discard_handler = fn

    def set_setup_retry_handler(self, fn):
        self._setup_retry_handler = fn

    def set_playback_state_handler(self, fn):
        self._playback_state_handler = fn

    def set_playback_control_handler(self, fn):
        self._playback_control_handler = fn

    def set_update_handlers(self, on_now, on_later):
        self._update_now_handler = on_now
        self._update_later_handler = on_later

    def _on_submit(self):
        if self._submit_handler is None:
            return
        text = self.input_entry.get().strip()
        if self._placeholder_active:
            return
        if not text:
            return
        self.input_entry.delete(0, tk.END)
        self._set_placeholder()
        self._refresh_send_state()
        self._submit_handler(text)
        self.input_entry.focus_set()

    def _on_mic(self):
        if self._mic_handler is None:
            return
        self._mic_handler()

    def _on_mic_mute_toggle(self):
        self._mic_muted = not self._mic_muted
        self.set_mic_muted(self._mic_muted)
        if self._mic_mute_toggle_handler is not None:
            self._mic_mute_toggle_handler(self._mic_muted)

    def set_mic_muted(self, muted: bool):
        self._mic_muted = bool(muted)
        if self._mic_muted:
            mute_icon = self._icon_refs.get("mute")
            self.mic_mute_btn.configure(
                image=mute_icon if mute_icon else "",
                text="Unmute Mic",
                fg="#8a1f1f",
                bg="#fdeeee",
                activebackground="#f9e1df",
            )
            self.mic_state_label.configure(text="Status: Muted", fg="#8a1f1f")
        else:
            mic_icon = self._icon_refs.get("mic_small")
            self.mic_mute_btn.configure(
                image=mic_icon if mic_icon else "",
                text="Mute Mic",
                fg="#23408f",
                bg="#f4f7ff",
                activebackground="#e7eeff",
            )
            self.mic_state_label.configure(text="Status: Unmuted", fg="#1f7a45")

    def _set_volume_scale(self, value: int):
        v = max(0, min(100, int(value)))
        self.volume_scale.set(v)
        self._on_volume_changed(str(v))

    def set_tts_volume(self, value: int):
        self._set_volume_scale(value)

    def _on_volume_changed(self, value):
        try:
            v = max(0, min(100, int(float(value))))
        except Exception:
            v = 100
        self.volume_value_label.configure(text=f"{v}%")
        if self._tts_volume_handler is not None:
            self._tts_volume_handler(v)

    def _on_pdf(self):
        if self._pdf_handler is None:
            return
        selected = filedialog.askopenfilename(
            title="Select PDF to summarize",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not selected:
            return
        self._pdf_handler(selected)

    def show_pending_pdf(self, pdf_path: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_pending_pdf, pdf_path)
            return
        self._pending_pdf_path = pdf_path
        self.pending_pdf_name_label.configure(text=Path(pdf_path).name)
        if not self.pending_pdf_frame.winfo_ismapped():
            self.pending_pdf_frame.pack(fill="x", pady=(0, 6))

    def clear_pending_pdf(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.clear_pending_pdf)
            return
        self._pending_pdf_path = ""
        if self.pending_pdf_frame.winfo_ismapped():
            self.pending_pdf_frame.pack_forget()

    def _on_pending_pdf_discard(self):
        self.clear_pending_pdf()
        if self._pdf_discard_handler is not None:
            self._pdf_discard_handler()

    def run(self):
        self.input_entry.focus_set()
        self.root.mainloop()

    def _set_placeholder(self):
        if self.input_entry.get().strip():
            return
        self._placeholder_active = True
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, self._placeholder_text)
        self.input_entry.configure(fg="#8b98ab")

    def _clear_placeholder(self):
        if not self._placeholder_active:
            return
        self.input_entry.delete(0, tk.END)
        self.input_entry.configure(fg="#1f2d3d")
        self._placeholder_active = False

    def _on_entry_focus_in(self, _event=None):
        self.entry_shell.configure(highlightbackground="#b9c9e8")
        self._clear_placeholder()
        self._refresh_send_state()

    def _on_entry_focus_out(self, _event=None):
        self.entry_shell.configure(highlightbackground="#dbe3f2")
        if not self.input_entry.get().strip():
            self._set_placeholder()
        self._refresh_send_state()

    def _on_entry_keypress(self, event):
        if self._placeholder_active:
            # Keep navigation keys working while placeholder is visible.
            if event.keysym in {"Left", "Right", "Up", "Down", "Home", "End", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}:
                return
            self._clear_placeholder()
            # Let current key continue so first typed character is not lost.
        self.root.after_idle(self._refresh_send_state)

    def _refresh_send_state(self):
        text = self.input_entry.get().strip()
        can_send = bool(text) and not self._placeholder_active
        self.send_btn.configure(
            state=(tk.NORMAL if can_send else tk.DISABLED),
            bg=("#2a5bd7" if can_send else "#b8c6e8"),
            activebackground=("#1f4ec2" if can_send else "#b8c6e8"),
            cursor=("hand2" if can_send else "arrow"),
        )

    def _use_quick_action(self, text: str):
        if self._placeholder_active:
            self.input_entry.delete(0, tk.END)
            self._placeholder_active = False
            self.input_entry.configure(fg="#1f2d3d")
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, text)
        self._refresh_send_state()
        self._on_submit()

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

    def _ensure_update_window(self):
        if self._update_window is not None:
            return self._update_window

        pane = tk.Toplevel(self.root)
        pane.title("SPARKY Update")
        pane.configure(bg="#eef3fb")
        pane.resizable(False, False)
        pane.transient(self.root)
        pane.withdraw()
        pane.protocol("WM_DELETE_WINDOW", self._on_update_later_clicked)

        shell = tk.Frame(
            pane,
            bg="#eef3fb",
            padx=14,
            pady=14,
            bd=0,
        )
        shell.pack(fill="both", expand=True)

        card = tk.Frame(
            shell,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#d8e2f3",
            bd=0,
            padx=16,
            pady=16,
        )
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg="#ffffff", bd=0)
        header.pack(fill="x")

        logo_img = self._icon_refs.get("app_logo")
        if logo_img is not None:
            tk.Label(header, image=logo_img, bg="#ffffff", bd=0).pack(side="left")

        header_text = tk.Frame(header, bg="#ffffff", bd=0)
        header_text.pack(side="left", padx=(10, 0))
        tk.Label(
            header_text,
            text="Patch Update Available",
            bg="#ffffff",
            fg="#17386d",
            font=("Poppins", 13, "bold"),
        ).pack(anchor="w")
        self._update_title_label = tk.Label(
            header_text,
            text="",
            bg="#ffffff",
            fg="#5a6a82",
            font=("Poppins", 9),
            justify="left",
            anchor="w",
        )
        self._update_title_label.pack(anchor="w", pady=(3, 0))

        self._update_message_label = tk.Label(
            card,
            text="",
            bg="#ffffff",
            fg="#30435f",
            font=("Poppins", 10),
            justify="left",
            anchor="w",
            wraplength=420,
        )
        self._update_message_label.pack(fill="x", pady=(14, 10))

        progress_wrap = tk.Frame(card, bg="#ffffff", bd=0)
        progress_wrap.pack(fill="x")
        self._update_progress = ttk.Progressbar(
            progress_wrap,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=0,
        )
        self._update_progress.pack(fill="x")
        self._update_note_label = tk.Label(
            card,
            text="",
            bg="#ffffff",
            fg="#607086",
            font=("Poppins", 9),
            justify="left",
            anchor="w",
        )
        self._update_note_label.pack(fill="x", pady=(8, 0))

        btn_row = tk.Frame(card, bg="#ffffff", bd=0)
        btn_row.pack(fill="x", pady=(16, 0))
        self._update_later_btn = tk.Button(
            btn_row,
            text="Remind Me Later",
            command=self._on_update_later_clicked,
            bg="#f4f7ff",
            fg="#264789",
            activebackground="#e6eefc",
            relief="flat",
            bd=0,
            font=("Poppins", 9, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        self._update_later_btn.pack(side="right")
        self._attach_button_hover(self._update_later_btn, "#f4f7ff", "#e6eefc")

        self._update_now_btn = tk.Button(
            btn_row,
            text="Update Now",
            command=self._on_update_now_clicked,
            bg="#2a5bd7",
            fg="#ffffff",
            activebackground="#1f4ec2",
            relief="flat",
            bd=0,
            font=("Poppins", 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self._update_now_btn.pack(side="right", padx=(0, 10))

        self._update_window = pane
        return pane

    def _show_update_window(self):
        pane = self._ensure_update_window()
        pane.deiconify()
        pane.lift()
        try:
            pane.grab_set()
        except Exception:
            pass
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(20, (self.root.winfo_width() - 500) // 2)
        y = self.root.winfo_rooty() + max(20, (self.root.winfo_height() - 260) // 3)
        pane.geometry(f"500x260+{x}+{y}")

    def show_update_prompt(self, version: str, details: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_update_prompt, version, details)
            return
        self._show_update_window()
        if self._update_title_label is not None:
            self._update_title_label.configure(text=f"Version {version} is ready to install.")
        if self._update_message_label is not None:
            self._update_message_label.configure(text=details or "A new SPARKY patch update is available.")
        if self._update_progress is not None:
            self._update_progress.configure(value=0)
        if self._update_note_label is not None:
            self._update_note_label.configure(text="Only the patch package will be downloaded, not the full installer.")
        if self._update_now_btn is not None:
            self._update_now_btn.configure(state=tk.NORMAL, text="Update Now", bg="#2a5bd7")
        if self._update_later_btn is not None:
            self._update_later_btn.configure(state=tk.NORMAL)

    def show_update_progress(self, text: str, value: float, note: str = ""):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_update_progress, text, value, note)
            return
        self._show_update_window()
        if self._update_message_label is not None:
            self._update_message_label.configure(text=text)
        if self._update_progress is not None:
            self._update_progress.configure(value=max(0.0, min(100.0, float(value))))
        if self._update_note_label is not None:
            self._update_note_label.configure(text=note or "")
        if self._update_now_btn is not None:
            self._update_now_btn.configure(state=tk.DISABLED, text="Updating...", bg="#9bb3eb")
        if self._update_later_btn is not None:
            self._update_later_btn.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def show_update_error(self, message: str):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.show_update_error, message)
            return
        self._show_update_window()
        if self._update_message_label is not None:
            self._update_message_label.configure(text=message)
        if self._update_note_label is not None:
            self._update_note_label.configure(text="The patch update could not be applied.")
        if self._update_now_btn is not None:
            self._update_now_btn.configure(state=tk.NORMAL, text="Try Again", bg="#2a5bd7")
        if self._update_later_btn is not None:
            self._update_later_btn.configure(state=tk.NORMAL)

    def close_update_prompt(self):
        if threading.get_ident() != self._main_thread_id:
            self.root.after(0, self.close_update_prompt)
            return
        if self._update_window is None:
            return
        try:
            self._update_window.grab_release()
        except Exception:
            pass
        self._update_window.withdraw()

    def _on_update_now_clicked(self):
        if self._update_now_handler is not None:
            self._update_now_handler()

    def _on_update_later_clicked(self):
        if self._update_later_handler is not None:
            self._update_later_handler()

    def _on_setup_retry(self):
        if self._setup_retry_handler is None:
            return
        self._setup_retry_handler()

