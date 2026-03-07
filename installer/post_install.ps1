param(
    [Parameter(Mandatory = $true)]
    [string]$AppDir,
    [string]$ProgressFile
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$LogPath = Join-Path $AppDir "installer_postinstall.log"
if (-not $ProgressFile) {
    $ProgressFile = Join-Path $AppDir "installer_progress.txt"
}

$signature = @"
using System;
using System.Runtime.InteropServices;
public static class NativeFontApi {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    public static extern int AddFontResourceW(string lpFileName);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint Msg,
        UIntPtr wParam,
        string lParam,
        uint fuFlags,
        uint uTimeout,
        out UIntPtr lpdwResult
    );
}
"@
Add-Type -TypeDefinition $signature -ErrorAction SilentlyContinue | Out-Null

$HWND_BROADCAST = [IntPtr]0xffff
$WM_FONTCHANGE = 0x001D
$SMTO_ABORTIFHUNG = 0x0002

function Normalize-ProgressText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return "" }
    return (($Value -replace "`r", " ") -replace "`n", " ").Trim()
}

function Write-ProgressState {
    param(
        [string]$Stage,
        [double]$Percent,
        [string]$Status,
        [string]$Detail = "",
        [Nullable[double]]$DownloadedBytes = $null,
        [Nullable[double]]$TotalBytes = $null,
        [bool]$Completed = $false,
        [bool]$Failed = $false
    )

    $safePercent = [math]::Max(0, [math]::Min(100, $Percent))
    $downloadedValue = 0
    $totalValue = 0
    if ($null -ne $DownloadedBytes) { $downloadedValue = [double]$DownloadedBytes }
    if ($null -ne $TotalBytes) { $totalValue = [double]$TotalBytes }
    $lines = @(
        "STAGE=$(Normalize-ProgressText $Stage)",
        "PERCENT=$([int][math]::Round($safePercent))",
        "STATUS=$(Normalize-ProgressText $Status)",
        "DETAIL=$(Normalize-ProgressText $Detail)",
        "DOWNLOADED_BYTES=$([string]::Format('{0:0}', $downloadedValue))",
        "TOTAL_BYTES=$([string]::Format('{0:0}', $totalValue))",
        "DOWNLOADED_MB=$([string]::Format('{0:N2}', ($downloadedValue / 1MB)))",
        "TOTAL_MB=$([string]::Format('{0:N2}', ($totalValue / 1MB)))",
        "COMPLETED=$([int]$Completed)",
        "FAILED=$([int]$Failed)",
        "UPDATED_AT=$((Get-Date).ToString('o'))"
    )

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try {
            [System.IO.File]::WriteAllLines($ProgressFile, $lines, $utf8)
            return
        }
        catch {
            if ($attempt -ge 9) {
                throw
            }
            Start-Sleep -Milliseconds 120
        }
    }
}

function Write-Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Value "[$stamp] $Message"
}

function Install-BundledFonts {
    $fontsDir = Join-Path $AppDir "fonts"
    if (-not (Test-Path -LiteralPath $fontsDir)) {
        Write-Log "Fonts directory not found: $fontsDir"
        return
    }

    $fontFiles = Get-ChildItem -LiteralPath $fontsDir -File | Where-Object {
        $_.Extension -in @(".ttf", ".otf")
    }
    if (-not $fontFiles) {
        Write-Log "No installable font files found in $fontsDir"
        return
    }

    $fontsTargetDir = Join-Path $env:WINDIR "Fonts"
    $fontsRegPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    $count = $fontFiles.Count
    $index = 0

    foreach ($font in $fontFiles) {
        $index += 1
        $progress = 52 + (($index / [double]$count) * 8)
        $destPath = Join-Path $fontsTargetDir $font.Name
        $typeSuffix = if ($font.Extension -ieq ".otf") { " (OpenType)" } else { " (TrueType)" }
        $regName = ($font.BaseName -replace "-", " ") + $typeSuffix

        Write-ProgressState -Stage "fonts" -Percent $progress -Status "Installing bundled fonts..." -Detail ("{0} of {1}: {2}" -f $index, $count, $font.Name)
        try {
            if (-not (Test-Path -LiteralPath $destPath)) {
                Copy-Item -LiteralPath $font.FullName -Destination $destPath -Force
            }
            [void][NativeFontApi]::AddFontResourceW($destPath)
            New-ItemProperty -Path $fontsRegPath -Name $regName -Value $font.Name -PropertyType String -Force | Out-Null
            if (Test-Path -LiteralPath $destPath) {
                Write-Log "Installed font: $($font.Name)"
            }
        }
        catch {
            if ((Test-Path -LiteralPath $destPath) -and ($_.Exception.Message -match "user-mapped section open")) {
                New-ItemProperty -Path $fontsRegPath -Name $regName -Value $font.Name -PropertyType String -Force | Out-Null
                Write-Log "Font already present/in use, kept existing copy: $($font.Name)"
            }
            else {
                Write-Log "Font install skipped/failed for $($font.Name): $($_.Exception.Message)"
            }
        }
    }

    $result = [UIntPtr]::Zero
    [void][NativeFontApi]::SendMessageTimeout(
        $HWND_BROADCAST,
        $WM_FONTCHANGE,
        [UIntPtr]::Zero,
        $null,
        $SMTO_ABORTIFHUNG,
        1000,
        [ref]$result
    )
    Write-ProgressState -Stage "fonts" -Percent 60 -Status "Fonts installed." -Detail "$count bundled fonts registered."
}

function Download-FileWithProgress {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$OutFile,
        [Parameter(Mandatory = $true)]
        [string]$Stage,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [double]$StartPercent,
        [double]$EndPercent
    )

    $client = $null
    $response = $null
    $inputStream = $null
    $outputStream = $null

    try {
        Add-Type -AssemblyName System.Net.Http | Out-Null
        $client = [System.Net.Http.HttpClient]::new()
        $response = $client.GetAsync($Uri, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
        [void]$response.EnsureSuccessStatusCode()

        if ($null -ne $response.Content.Headers.ContentLength) {
            $totalBytes = [double]$response.Content.Headers.ContentLength
        }
        else {
            $totalBytes = 0.0
        }
        $inputStream = $response.Content.ReadAsStreamAsync().Result
        $parentDir = Split-Path -Parent $OutFile
        if ($parentDir -and -not (Test-Path -LiteralPath $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }
        if (Test-Path -LiteralPath $OutFile) {
            try {
                Remove-Item -LiteralPath $OutFile -Force -ErrorAction Stop
            }
            catch {
                throw "Could not replace existing download target: $OutFile. $($_.Exception.Message)"
            }
        }
        $outputStream = [System.IO.File]::Open($OutFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)

        $buffer = New-Object byte[] 1048576
        $downloadedBytes = 0.0
        $lastUpdate = [System.Diagnostics.Stopwatch]::StartNew()
        Write-ProgressState -Stage $Stage -Percent $StartPercent -Status $Status -Detail "Starting download..." -DownloadedBytes 0 -TotalBytes $totalBytes

        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $outputStream.Write($buffer, 0, $read)
            $downloadedBytes += $read

            if ($lastUpdate.ElapsedMilliseconds -ge 200 -or ($totalBytes -gt 0 -and $downloadedBytes -ge $totalBytes)) {
                if ($totalBytes -gt 0) {
                    $ratio = [math]::Min(1.0, $downloadedBytes / $totalBytes)
                    $percent = $StartPercent + (($EndPercent - $StartPercent) * $ratio)
                    $detail = ("{0:N2} MB / {1:N2} MB" -f ($downloadedBytes / 1MB), ($totalBytes / 1MB))
                }
                else {
                    $percent = $StartPercent
                    $detail = ("{0:N2} MB downloaded" -f ($downloadedBytes / 1MB))
                }

                Write-ProgressState -Stage $Stage -Percent $percent -Status $Status -Detail $detail -DownloadedBytes $downloadedBytes -TotalBytes $totalBytes
                $lastUpdate.Restart()
            }
        }

        Write-ProgressState -Stage $Stage -Percent $EndPercent -Status $Status -Detail ("{0:N2} MB downloaded" -f ($downloadedBytes / 1MB)) -DownloadedBytes $downloadedBytes -TotalBytes $totalBytes
    }
    finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }
        if ($client) { $client.Dispose() }
    }
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Add-MachinePathEntry {
    param([string]$Entry)
    if (-not (Test-Path -LiteralPath $Entry)) { return }
    $current = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $parts = @()
    if ($current) { $parts = $current.Split(";") | Where-Object { $_ -and $_.Trim() } }
    if ($parts -contains $Entry) { return }
    $newPath = ($parts + $Entry) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Log "Added PATH entry: $Entry"
}

function Get-Python311Exe {
    try {
        $exe = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
    } catch {}
    try {
        $cmd = Get-Command python -ErrorAction Stop
        $v = & $cmd.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($v.Trim() -eq "3.11") { return $cmd.Source }
    } catch {}
    return $null
}

function Ensure-Python311 {
    $py = Get-Python311Exe
    if ($py) {
        Write-Log "Python 3.11 detected: $py"
        Write-ProgressState -Stage "python" -Percent 12 -Status "Python 3.11 already installed." -Detail $py
        return $py
    }

    Write-Log "Python 3.11 not found. Installing silently..."
    $installer = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
    if (-not (Test-Path -LiteralPath $installer)) {
        Download-FileWithProgress `
            -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
            -OutFile $installer `
            -Stage "python-download" `
            -Status "Downloading Python 3.11 installer..." `
            -StartPercent 3 `
            -EndPercent 12
    }
    else {
        Write-ProgressState -Stage "python-download" -Percent 12 -Status "Python 3.11 installer already cached." -Detail $installer
    }

    Write-ProgressState -Stage "python-install" -Percent 14 -Status "Installing Python 3.11..." -Detail "Running silent installer..."
    $args = @(
        "/quiet",
        "InstallAllUsers=1",
        "PrependPath=1",
        "Include_pip=1",
        "Include_test=0",
        "SimpleInstall=1"
    )
    $p = Start-Process -FilePath $installer -ArgumentList $args -PassThru -Wait -WindowStyle Hidden
    if ($p.ExitCode -ne 0) {
        throw "Python installer failed with exit code $($p.ExitCode)."
    }
    Refresh-Path
    $py = Get-Python311Exe
    if (-not $py) { throw "Python 3.11 still not found after installation." }
    Write-Log "Python installed: $py"
    Write-ProgressState -Stage "python-install" -Percent 20 -Status "Python 3.11 installed." -Detail $py
    return $py
}

function Ensure-PythonDeps {
    param([string]$PythonExe)
    $req = Join-Path $AppDir "requirements.txt"
    if (-not (Test-Path -LiteralPath $req)) {
        throw "requirements.txt not found at $req"
    }
    Write-Log "Installing Python dependencies..."
    Write-ProgressState -Stage "python-deps" -Percent 24 -Status "Installing Python dependencies..." -Detail "Upgrading pip, setuptools, and wheel..."
    & $PythonExe -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed." }
    Write-ProgressState -Stage "python-deps" -Percent 32 -Status "Installing Python dependencies..." -Detail "Installing requirements.txt..."
    & $PythonExe -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed." }

    # Needed for browser features when enabled.
    Write-ProgressState -Stage "python-deps" -Percent 44 -Status "Installing browser runtime..." -Detail "Installing Playwright Chromium..."
    & $PythonExe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Playwright browser install failed. Continuing (browser features may be limited)."
    }
    Write-ProgressState -Stage "python-deps" -Percent 50 -Status "Python dependencies installed." -Detail "Runtime dependencies are ready."
}

function Get-OllamaExe {
    $candidates = @(
        "$env:ProgramFiles\Ollama\ollama.exe",
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Ollama\ollama.exe"
    )

    try {
        $cmd = Get-Command ollama -ErrorAction Stop
        return $cmd.Source
    } catch {
        foreach ($candidate in $candidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                return $candidate
            }
        }
        return $null
    }
}

function Ensure-Ollama {
    $ollama = Get-OllamaExe
    if (-not $ollama) {
        Write-ProgressState -Stage "ollama-check" -Percent 72 -Status "Ollama is required before setup can continue." -Detail "Install Ollama manually, then run SPARKY setup again."
        throw "Ollama is not installed. Install Ollama manually, then run SPARKY setup again."
    }
    Add-MachinePathEntry (Split-Path -Parent $ollama)
    Refresh-Path
    Write-Log "Ollama detected: $ollama"
    Write-ProgressState -Stage "ollama-check" -Percent 78 -Status "Ollama detected." -Detail $ollama
    return $ollama
}

function Verify-OllamaInstall {
    param([string]$OllamaExe)
    Write-ProgressState -Stage "ollama-verify" -Percent 80 -Status "Verifying Ollama install..." -Detail $OllamaExe
    & $OllamaExe --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama executable did not respond after install."
    }
    Write-Log "Ollama install verified."
}

function Ensure-OllamaService {
    param([string]$OllamaExe)
    & $OllamaExe list *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Ollama service is already running."
        Write-ProgressState -Stage "ollama-service" -Percent 84 -Status "Ollama service already running." -Detail "Local API is reachable."
        return
    }

    Write-Log "Starting Ollama service..."
    Write-ProgressState -Stage "ollama-service" -Percent 82 -Status "Starting Ollama service..." -Detail "Launching ollama serve..."
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        Write-ProgressState -Stage "ollama-service" -Percent (82 + [math]::Min(2, ($i / 15.0) * 2)) -Status "Waiting for Ollama service..." -Detail "Checking local API availability..."
        & $OllamaExe list *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Ollama service started."
            Write-ProgressState -Stage "ollama-service" -Percent 84 -Status "Ollama service started." -Detail "Local API is reachable."
            return
        }
    }
    throw "Ollama service did not start in time."
}

function Test-OllamaModelInstalled {
    param([string]$OllamaExe, [string]$ModelName)
    $output = & $OllamaExe list 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    foreach ($line in ($output | Out-String).Split([Environment]::NewLine)) {
        $trimmed = $line.Trim()
        if (-not $trimmed) { continue }
        if ($trimmed.ToLower().StartsWith("name")) { continue }
        $name = ($trimmed -split "\s+")[0]
        if ($name -eq $ModelName) {
            return $true
        }
    }
    return $false
}

function Ensure-OllamaModel {
    param([string]$OllamaExe, [string]$ModelName)
    if (Test-OllamaModelInstalled -OllamaExe $OllamaExe -ModelName $ModelName) {
        Write-Log "Model already present: $ModelName"
        Write-ProgressState -Stage "model" -Percent 96 -Status "Model already available." -Detail $ModelName
        return
    }

    Write-Log "Pulling model: $ModelName"
    Write-ProgressState -Stage "model" -Percent 86 -Status "Opening model download terminal..." -Detail "A PowerShell window will open and run: ollama pull $ModelName"
    $psCommand = "`$host.UI.RawUI.WindowTitle = 'SPARKY Model Setup'; & '" + $OllamaExe.Replace("'", "''") + "' pull '" + $ModelName.Replace("'", "''") + "'; exit `$LASTEXITCODE"
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $psCommand) -PassThru -WindowStyle Normal
    $tick = 0
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 1
        $tick += 1
        $percent = 86 + [math]::Min(7, $tick * 0.15)
        $elapsedMin = [math]::Floor($tick / 60)
        $elapsedSec = $tick % 60
        Write-ProgressState -Stage "model" -Percent $percent -Status "Pulling model $ModelName..." -Detail ("Waiting for the model terminal to finish... ({0}m {1:00}s elapsed)" -f $elapsedMin, $elapsedSec)
    }
    if ($proc.ExitCode -ne 0) {
        throw "Failed to pull model $ModelName. The model download terminal exited with code $($proc.ExitCode)."
    }
    Write-ProgressState -Stage "model" -Percent 94 -Status "Model download completed." -Detail $ModelName
}

function Verify-OllamaModel {
    param([string]$OllamaExe, [string]$ModelName)
    Write-ProgressState -Stage "model-verify" -Percent 96 -Status "Verifying model..." -Detail $ModelName
    if (-not (Test-OllamaModelInstalled -OllamaExe $OllamaExe -ModelName $ModelName)) {
        throw "Model verification failed for $ModelName."
    }
    Write-Log "Model verified: $ModelName"
}

function Ensure-OllamaReady {
    param([string]$OllamaExe)
    Write-ProgressState -Stage "ollama-ready" -Percent 99 -Status "Serving Ollama locally..." -Detail "Ensuring Ollama is ready for SPARKY..."
    Ensure-OllamaService -OllamaExe $OllamaExe
}

function Verify-OllamaEndpoint {
    Write-ProgressState -Stage "verify" -Percent 99 -Status "Verifying Ollama endpoint..." -Detail "Checking local API..."
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) {
            throw "Unexpected HTTP status: $($resp.StatusCode)"
        }
    } catch {
        throw "Ollama endpoint verification failed: $($_.Exception.Message)"
    }
}

try {
    Write-Log "Starting post-install setup..."
    Write-ProgressState -Stage "start" -Percent 1 -Status "Preparing SPARKY runtime..." -Detail "Configuring local dependencies..."

    Add-MachinePathEntry (Join-Path $AppDir "ffmpeg-8.0.1-essentials_build\bin")
    Add-MachinePathEntry (Join-Path $AppDir "piper")
    Refresh-Path
    Install-BundledFonts

    $python = Ensure-Python311
    Ensure-PythonDeps -PythonExe $python

    $ollama = Ensure-Ollama
    Verify-OllamaInstall -OllamaExe $ollama
    Ensure-OllamaService -OllamaExe $ollama
    Ensure-OllamaModel -OllamaExe $ollama -ModelName "llama3:8b"
    Verify-OllamaModel -OllamaExe $ollama -ModelName "llama3:8b"
    Ensure-OllamaReady -OllamaExe $ollama
    Verify-OllamaEndpoint

    Write-Log "Post-install setup completed successfully."
    Write-ProgressState -Stage "done" -Percent 100 -Status "SPARKY runtime is ready." -Detail "Ollama and llama3:8b are installed." -Completed $true
    exit 0
}
catch {
    Write-Log "Post-install failed: $($_.Exception.Message)"
    Write-ProgressState -Stage "failed" -Percent 100 -Status "SPARKY setup failed." -Detail $_.Exception.Message -Completed $true -Failed $true
    Write-Error $_
    exit 1
}
