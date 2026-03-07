from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path

import requests

from app_version import APP_VERSION


@dataclass
class UpdateInfo:
    version: str
    tag_name: str
    notes: str
    html_url: str
    published_at: str
    patch_asset_name: str
    patch_asset_url: str


class AppUpdater:
    def __init__(self, app_root: Path):
        self.app_root = Path(app_root)
        self.config = self._load_config()
        self.state_dir = self._resolve_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "update_state.json"

    def _load_config(self) -> dict:
        defaults = {
            "github_repo": "ahansardar/SPARKY",
            "release_api": "https://api.github.com/repos/{repo}/releases/latest",
            "release_page": "https://github.com/{repo}/releases/latest",
            "patch_asset_names": [
                "SPARKY-patch-{version}.zip",
                "SPARKY-patch.zip",
            ],
            "remind_later_hours": 24,
        }
        path = self.app_root / "config" / "update.json"
        if not path.exists():
            return defaults
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(data, dict):
            return defaults
        merged = defaults.copy()
        merged.update(data)
        return merged

    def _resolve_state_dir(self) -> Path:
        if os.name == "nt":
            base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
            return base / "SPARKY"
        return Path.home() / ".sparky"

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self, payload: dict) -> None:
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def remind_later(self, version: str) -> None:
        hours = int(self.config.get("remind_later_hours") or 24)
        remind_after = datetime.now(timezone.utc) + timedelta(hours=max(1, hours))
        self._save_state(
            {
                "skip_version": version,
                "remind_after": remind_after.isoformat(),
            }
        )

    def clear_reminder(self) -> None:
        if self.state_path.exists():
            try:
                self.state_path.unlink()
            except Exception:
                pass

    def check_for_update(self) -> UpdateInfo | None:
        repo = str(self.config.get("github_repo") or "").strip()
        if not repo:
            return None
        api_url = str(self.config.get("release_api") or "").format(repo=repo)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SPARKY/{APP_VERSION}",
        }
        resp = requests.get(api_url, headers=headers, timeout=8)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            return None
        if payload.get("draft") or payload.get("prerelease"):
            return None

        version = self._normalize_version(str(payload.get("tag_name") or payload.get("name") or ""))
        if not version or self._compare_versions(version, APP_VERSION) <= 0:
            return None

        state = self._load_state()
        if state.get("skip_version") == version:
            remind_after = str(state.get("remind_after") or "").strip()
            if remind_after:
                try:
                    when = datetime.fromisoformat(remind_after)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) < when:
                        return None
                except Exception:
                    pass

        assets = payload.get("assets") or []
        if not isinstance(assets, list):
            assets = []
        asset = self._pick_patch_asset(assets, version)
        if not asset:
            return None

        return UpdateInfo(
            version=version,
            tag_name=str(payload.get("tag_name") or version),
            notes=self._format_notes(str(payload.get("body") or "")),
            html_url=str(payload.get("html_url") or str(self.config.get("release_page") or "").format(repo=repo)),
            published_at=str(payload.get("published_at") or ""),
            patch_asset_name=str(asset.get("name") or ""),
            patch_asset_url=str(asset.get("browser_download_url") or ""),
        )

    def _pick_patch_asset(self, assets: list[dict], version: str) -> dict | None:
        wanted = []
        for pattern in self.config.get("patch_asset_names") or []:
            wanted.append(str(pattern).format(version=version))
        lowered = {name.lower(): name for name in wanted}
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower() in lowered and asset.get("browser_download_url"):
                return asset
        return None

    def _normalize_version(self, raw: str) -> str:
        value = raw.strip()
        if value.lower().startswith("v"):
            value = value[1:]
        return value

    def _version_tuple(self, value: str) -> tuple[int, ...]:
        pieces = []
        for part in self._normalize_version(value).split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            pieces.append(int(digits or "0"))
        while len(pieces) < 3:
            pieces.append(0)
        return tuple(pieces[:3])

    def _compare_versions(self, left: str, right: str) -> int:
        lv = self._version_tuple(left)
        rv = self._version_tuple(right)
        if lv < rv:
            return -1
        if lv > rv:
            return 1
        return 0

    def _format_notes(self, body: str) -> str:
        lines = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.startswith(("-", "*")):
                line = line[1:].strip()
            lines.append(line)
            if len(lines) >= 5:
                break
        if not lines:
            return "A new SPARKY patch update is available."
        return "\n".join(lines)

    def download_and_install_patch(self, update: UpdateInfo, progress_cb) -> tuple[bool, str]:
        if not getattr(sys, "frozen", False):
            return False, "Patch updates are only available in the installed desktop build."

        download_dir = Path(tempfile.mkdtemp(prefix="sparky_patch_"))
        zip_path = download_dir / update.patch_asset_name
        progress_cb("Downloading patch update...", 5, "Connecting to GitHub release asset...")

        headers = {"User-Agent": f"SPARKY/{APP_VERSION}"}
        with requests.get(update.patch_asset_url, headers=headers, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            with zip_path.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = 5 + (downloaded / total) * 75
                        note = f"{downloaded / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB"
                    else:
                        pct = 5
                        note = f"{downloaded / (1024 * 1024):.2f} MB downloaded"
                    progress_cb("Downloading patch update...", pct, note)

        progress_cb("Preparing patch installer...", 84, "Verifying downloaded patch package...")
        script_path = self._write_patch_script(download_dir)
        ok = self._launch_patch_installer(script_path, zip_path)
        if not ok:
            return False, "Could not start the elevated patch installer."

        self.clear_reminder()
        progress_cb("Applying patch update...", 100, "SPARKY will close, patch itself, and restart.")
        return True, ""

    def _write_patch_script(self, folder: Path) -> Path:
        script_path = folder / "apply_patch_update.ps1"
        script = textwrap.dedent(
            r"""
            param(
                [Parameter(Mandatory = $true)][string]$ZipPath,
                [Parameter(Mandatory = $true)][string]$AppDir,
                [Parameter(Mandatory = $true)][string]$ExePath,
                [Parameter(Mandatory = $true)][int]$ProcessId
            )

            $ErrorActionPreference = "Stop"
            $stage = Join-Path $env:TEMP ("sparky_apply_" + [guid]::NewGuid().ToString("N"))
            $contentRoot = $stage

            try {
                if ($ProcessId -gt 0) {
                    try {
                        Wait-Process -Id $ProcessId -Timeout 180
                    } catch {
                        Start-Sleep -Seconds 3
                    }
                }

                New-Item -ItemType Directory -Path $stage -Force | Out-Null
                Expand-Archive -LiteralPath $ZipPath -DestinationPath $stage -Force

                $entries = Get-ChildItem -LiteralPath $stage
                if ($entries.Count -eq 1 -and $entries[0].PSIsContainer) {
                    $contentRoot = $entries[0].FullName
                }

                Get-ChildItem -LiteralPath $contentRoot -Force | ForEach-Object {
                    Copy-Item -LiteralPath $_.FullName -Destination $AppDir -Recurse -Force
                }

                Start-Process -FilePath $ExePath | Out-Null
            }
            finally {
                Start-Sleep -Seconds 1
                Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
            }
            """
        ).strip()
        script_path.write_text(script, encoding="utf-8")
        return script_path

    def _launch_patch_installer(self, script_path: Path, zip_path: Path) -> bool:
        exe_path = Path(sys.executable).resolve()
        if os.name != "nt":
            return False
        args = subprocess.list2cmdline(
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-ZipPath",
                str(zip_path),
                "-AppDir",
                str(self.app_root),
                "-ExePath",
                str(exe_path),
                "-ProcessId",
                str(os.getpid()),
            ]
        )
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "powershell.exe",
            args,
            None,
            1,
        )
        return rc > 32
