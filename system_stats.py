import shutil
import subprocess
import time
from typing import Any

import psutil


def _safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def internet_speed_test_mbps(
    timeout_sec: int = 12,
    down_bytes: int = 8_000_000,
    up_bytes: int = 1_500_000,
) -> tuple[float | None, float | None]:
    """
    Active internet speed test (download/upload) in Mbps using speedtest-cli library.
    """
    try:
        import speedtest  # type: ignore

        # keep params for compatibility with callers; library controls transfer size.
        _ = (timeout_sec, down_bytes, up_bytes)
        st = speedtest.Speedtest()
        st.get_best_server()
        down = st.download()
        up = st.upload(pre_allocate=False)
        down_mbps = _safe_float(down)
        up_mbps = _safe_float(up)
        if down_mbps is not None:
            down_mbps /= 1_000_000.0
        if up_mbps is not None:
            up_mbps /= 1_000_000.0
        if down_mbps is not None and down_mbps <= 0.01:
            down_mbps = None
        if up_mbps is not None and up_mbps <= 0.01:
            up_mbps = None
        return down_mbps, up_mbps
    except Exception:
        return None, None


def _cpu_temperature_c() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    if not temps:
        return None
    for entries in temps.values():
        for ent in entries:
            current = _safe_float(getattr(ent, "current", None))
            if current is not None:
                return current
    return None


def _gpu_usage_percent() -> float | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            encoding="utf-8",
            errors="ignore",
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return None
        return _safe_float(line[0].strip())
    except Exception:
        return None


def collect_system_stats(
    prev_net: tuple[int, int, float] | None = None,
    speed_test: tuple[float | None, float | None] | None = None,
) -> tuple[dict[str, Any], tuple[int, int, float]]:
    cpu_usage = _safe_float(psutil.cpu_percent(interval=None), 0.0) or 0.0
    ram_usage = _safe_float(psutil.virtual_memory().percent, 0.0) or 0.0
    disk_usage = _safe_float(psutil.disk_usage("/").percent, 0.0) or 0.0
    cpu_temp = _cpu_temperature_c()
    gpu_usage = _gpu_usage_percent()

    sent_now = recv_now = 0
    now_ts = time.time()
    upload_mbps = None
    download_mbps = None
    if speed_test is not None:
        download_mbps, upload_mbps = speed_test

    stats = {
        "cpu_temp_c": cpu_temp,
        "gpu_usage_percent": gpu_usage,
        "cpu_usage_percent": cpu_usage,
        "ram_usage_percent": ram_usage,
        "storage_usage_percent": disk_usage,
        "upload_mbps": upload_mbps,
        "download_mbps": download_mbps,
    }
    return stats, (sent_now, recv_now, now_ts)


def system_suggestions(stats: dict[str, Any]) -> list[str]:
    tips: list[str] = []
    cpu = _safe_float(stats.get("cpu_usage_percent"))
    ram = _safe_float(stats.get("ram_usage_percent"))
    disk = _safe_float(stats.get("storage_usage_percent"))
    cpu_temp = _safe_float(stats.get("cpu_temp_c"))
    gpu = _safe_float(stats.get("gpu_usage_percent"))
    down = _safe_float(stats.get("download_mbps"))

    if cpu is not None and cpu >= 85:
        tips.append("CPU usage is high. Close heavy background apps and reduce parallel workloads.")
    if ram is not None and ram >= 85:
        tips.append("RAM usage is high. Close memory-heavy apps or restart to clear memory pressure.")
    if disk is not None and disk >= 90:
        tips.append("Storage is almost full. Free at least 10-20% disk space for smoother performance.")
    if cpu_temp is not None and cpu_temp >= 85:
        tips.append("CPU temperature is high. Improve airflow, clean vents, and avoid sustained heavy load.")
    if gpu is not None and gpu >= 95:
        tips.append("GPU usage is near maximum. Lower graphics load or close GPU-heavy programs.")
    if down is not None and down < 2.0:
        tips.append("Network download speed is low. Check Wi-Fi signal, background downloads, or switch network.")

    if not tips:
        tips.append("System looks healthy right now.")
    return tips


def format_system_stats_report(stats: dict[str, Any], include_suggestions: bool = True) -> str:
    def f_pct(v):
        vv = _safe_float(v)
        return "N/A" if vv is None else f"{vv:.1f}%"

    def f_temp(v):
        vv = _safe_float(v)
        return "Not available" if vv is None else f"{vv:.1f} C"

    def f_mbps(v):
        vv = _safe_float(v)
        return "Not tested" if vv is None else f"{(vv / 8.0):.2f} MB/s"

    lines = [
        "System Resource Stats:",
        f"* CPU temperature: {f_temp(stats.get('cpu_temp_c'))}",
        f"* GPU usage: {f_pct(stats.get('gpu_usage_percent'))}",
        f"* CPU usage: {f_pct(stats.get('cpu_usage_percent'))}",
        f"* RAM usage: {f_pct(stats.get('ram_usage_percent'))}",
        f"* Storage usage: {f_pct(stats.get('storage_usage_percent'))}",
        f"* Network upload: {f_mbps(stats.get('upload_mbps'))}",
        f"* Network download: {f_mbps(stats.get('download_mbps'))}",
    ]
    if include_suggestions:
        tips = system_suggestions(stats)
        lines.append("")
        lines.append("Suggestions:")
        for tip in tips:
            lines.append(f"* {tip}")
    return "\n".join(lines)
