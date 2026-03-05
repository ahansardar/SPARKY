"""
actions/screen_processor.py
Ollama vision-based screen/camera analysis.
"""

import base64
import io
import threading
from pathlib import Path

import cv2
import mss
import mss.tools
import requests

try:
    import PIL.Image

    _PIL_OK = True
except ImportError:
    _PIL_OK = False

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
VISION_MODEL = "llava:7b"
IMG_MAX_W = 960
IMG_MAX_H = 540
JPEG_Q = 70

_start_lock = threading.Lock()


def _to_jpeg(img_bytes: bytes) -> bytes:
    if not _PIL_OK:
        return img_bytes
    img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
    return buf.getvalue()


def _capture_screenshot() -> bytes:
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)
    return _to_jpeg(png_bytes)


def _capture_camera() -> bytes:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("Camera could not be opened at index 0.")
    for _ in range(8):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("Could not capture camera frame.")

    if _PIL_OK:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
        return buf.getvalue()

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    return buf.tobytes()


def _analyze_with_ollama(image_bytes: bytes, user_text: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "You are SPARKY. Analyze this image with technical precision and concise wording. "
        "Respond in max 3 short sentences.\n\n"
        f"User request: {user_text}"
    )
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
    }
    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "").strip()


def _ensure_started(player=None):
    # Kept for compatibility with existing call sites.
    with _start_lock:
        if player:
            pass


def screen_process(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None,
) -> bool:
    user_text = (parameters or {}).get("text") or (parameters or {}).get("user_text", "")
    user_text = (user_text or "").strip()
    if not user_text:
        print("[ScreenProcess] No user_text provided.")
        return False

    angle = (parameters or {}).get("angle", "screen").lower().strip()
    _ensure_started(player=player)

    try:
        if angle == "camera":
            image_bytes = _capture_camera()
            print("[ScreenProcess] Camera captured")
        else:
            image_bytes = _capture_screenshot()
            print("[ScreenProcess] Screen captured")
    except Exception as e:
        print(f"[ScreenProcess] Capture error: {e}")
        return False

    try:
        result = _analyze_with_ollama(image_bytes, user_text)
        if player and result:
            player.write_log(f"SPARKY: {result}")
        print(f"[ScreenProcess] {result}")
        return True
    except Exception as e:
        print(f"[ScreenProcess] Analyze error: {e}")
        return False


def warmup_session(player=None):
    _ensure_started(player=player)
