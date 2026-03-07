param(
    [string]$InnoCompilerPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath $InnoCompilerPath)) {
    throw "Inno Setup compiler not found: $InnoCompilerPath"
}

& $InnoCompilerPath ".\SPARKY.iss"

Write-Host "Installer generated under ..\\dist-installer\\SPARKY-Setup.exe"
