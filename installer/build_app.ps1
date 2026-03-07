param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

if ($Clean) {
    if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
    if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --name SPARKY `
  --icon assets\icon.ico `
  --paths . `
  --collect-submodules actions `
  --collect-submodules agent `
  --collect-submodules memory `
  --collect-submodules src `
  --hidden-import tkinter `
  --hidden-import PIL.Image `
  --hidden-import PIL.ImageTk `
  --hidden-import cairosvg `
  --hidden-import speedtest `
  --hidden-import openwakeword.model `
  --hidden-import faster_whisper `
  --hidden-import yt_dlp `
  --hidden-import youtube_transcript_api `
  --hidden-import playwright.async_api `
  src\ai_agent.py

Write-Host "Build complete: .\\dist\\SPARKY.exe"
