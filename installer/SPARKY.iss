#define AppName "SPARKY"
#define AppVersion "1.1.0"
#define AppPublisher "Ahan Sardar"
#define AppExeName "SPARKY.exe"

[Setup]
AppId={{F2F6E6D9-D5E3-4D69-8A1D-7D55D39C79A1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
OutputDir=..\dist-installer
OutputBaseFilename=SPARKY-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
ChangesEnvironment=yes
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "launchapp"; Description: "Launch SPARKY after installation"; Flags: unchecked

[Files]
; Built executable
Source: "..\dist\SPARKY.exe"; DestDir: "{app}"; Flags: ignoreversion

; Core folders
Source: "..\actions\*"; DestDir: "{app}\actions"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\agent\*"; DestDir: "{app}\agent"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\config\*"; DestDir: "{app}\config"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\fonts\*"; DestDir: "{app}\fonts"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\memory\*"; DestDir: "{app}\memory"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\models\*"; DestDir: "{app}\models"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\piper\*"; DestDir: "{app}\piper"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\ffmpeg-8.0.1-essentials_build\*"; DestDir: "{app}\ffmpeg-8.0.1-essentials_build"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\src\*"; DestDir: "{app}\src"; Flags: recursesubdirs createallsubdirs ignoreversion

; Root runtime files
Source: "..\ui.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\system_stats.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Installer helper scripts
Source: "post_install.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Code]
const
  MinRAMGB = 8;
  RecRAMGB = 16;
  MinCores = 4;
  RecCores = 6;
  MinDiskGB = 20;
  RecDiskGB = 30;

var
  ScanPage: TWizardPage;
  ScanMemo: TMemo;
  ScanRan: Boolean;
  ScanPassed: Boolean;
  ScanReport: string;
  ScanBlockReason: string;
  PostInstallPage: TOutputProgressWizardPage;
  PostInstallProgressFile: string;

const
  STILL_ACTIVE = 259;
  PROCESS_QUERY_INFORMATION = $0400;
  SYNCHRONIZE = $00100000;

function GetExitCodeProcess(hProcess: Integer; var ExitCode: Integer): Boolean;
  external 'GetExitCodeProcess@kernel32.dll stdcall';
function CloseHandle(hObject: Integer): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function OpenProcess(dwDesiredAccess: Integer; bInheritHandle: Boolean; dwProcessId: Integer): Integer;
  external 'OpenProcess@kernel32.dll stdcall';
function GetPhysicallyInstalledSystemMemory(var TotalMemoryInKilobytes: Int64): Boolean;
  external 'GetPhysicallyInstalledSystemMemory@kernel32.dll stdcall';
function InternetGetConnectedState(var Flags: Integer; Reserved: Integer): Boolean;
  external 'InternetGetConnectedState@wininet.dll stdcall';

function ParseValue(const Source, Key: string): string;
var
  P, E: Integer;
  Needle: string;
begin
  Result := '';
  Needle := Key + '=';
  P := Pos(Needle, Source);
  if P <= 0 then
    Exit;
  P := P + Length(Needle);
  E := Pos(#10, Copy(Source, P, MaxInt));
  if E <= 0 then
    Result := Trim(Copy(Source, P, MaxInt))
  else
    Result := Trim(Copy(Source, P, E - 1));
end;

function BoolText(const Value: Boolean): string;
begin
  if Value then
    Result := 'True'
  else
    Result := 'False';
end;

function ExecPowerShellCapture(const Cmd: string; var Output: string): Boolean;
var
  TmpFile: string;
  Params: string;
  ResultCode: Integer;
  RawOutput: AnsiString;
begin
  TmpFile := ExpandConstant('{tmp}\sparky_scan.txt');
  DeleteFile(TmpFile);
  Params :=
    '-NoProfile -ExecutionPolicy Bypass -Command "' + Cmd + ' | Out-File -FilePath ''' + TmpFile + ''' -Encoding utf8"';
  Result := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  if (not Result) or (ResultCode <> 0) then
  begin
    Output := '';
    Result := False;
    Exit;
  end;
  Result := LoadStringFromFile(TmpFile, RawOutput);
  if Result then
    Output := RawOutput
  else
    Output := '';
end;

procedure RunSystemScan();
var
  Version: TWindowsVersion;
  FreeMB, TotalMB: Cardinal;
  DiskPath: string;
  RamGB, Cores, DiskGB: Integer;
  NetOK: Boolean;
  WarnText: string;
  TotalMemoryKB: Int64;
  NetFlags: Integer;
begin
  if ScanRan then
    Exit;

  ScanRan := True;
  ScanPassed := True;
  ScanBlockReason := '';
  WarnText := '';

  GetWindowsVersionEx(Version);
  if (Version.Major < 10) then
  begin
    ScanPassed := False;
    ScanBlockReason := ScanBlockReason + '- Windows 10/11 is required.' + #13#10;
  end;

  if not IsWin64 then
  begin
    ScanPassed := False;
    ScanBlockReason := ScanBlockReason + '- 64-bit Windows is required.' + #13#10;
  end;

  DiskPath := ExtractFileDrive(ExpandConstant('{autopf}')) + '\';
  if not GetSpaceOnDisk(DiskPath, True, FreeMB, TotalMB) then
  begin
    FreeMB := 0;
  end;
  DiskGB := FreeMB div 1024;
  if DiskGB < MinDiskGB then
  begin
    ScanPassed := False;
    ScanBlockReason := ScanBlockReason +
      Format('- At least %d GB free disk space is required on %s (found %d GB).', [MinDiskGB, DiskPath, DiskGB]) + #13#10;
  end
  else if DiskGB < RecDiskGB then
  begin
    WarnText := WarnText +
      Format('- Disk free space is below recommended (%d GB found, %d GB recommended).', [DiskGB, RecDiskGB]) + #13#10;
  end;

  if GetPhysicallyInstalledSystemMemory(TotalMemoryKB) then
    RamGB := TotalMemoryKB div (1024 * 1024)
  else
    RamGB := 0;

  Cores := StrToIntDef(GetEnv('NUMBER_OF_PROCESSORS'), 0);

  NetFlags := 0;
  NetOK := InternetGetConnectedState(NetFlags, 0);

  if RamGB <= 0 then
  begin
    WarnText := WarnText + '- Could not verify installed RAM. Continuing without blocking on RAM check.' + #13#10;
  end
  else if RamGB < MinRAMGB then
  begin
    ScanPassed := False;
    ScanBlockReason := ScanBlockReason +
      Format('- At least %d GB RAM is required (found %d GB).', [MinRAMGB, RamGB]) + #13#10;
  end
  else if RamGB < RecRAMGB then
  begin
    WarnText := WarnText +
      Format('- RAM is below recommended (%d GB found, %d GB recommended).', [RamGB, RecRAMGB]) + #13#10;
  end;

  if Cores <= 0 then
  begin
    WarnText := WarnText + '- Could not verify CPU core count. Continuing without blocking on CPU check.' + #13#10;
  end
  else if Cores < MinCores then
  begin
    ScanPassed := False;
    ScanBlockReason := ScanBlockReason +
      Format('- At least %d logical CPU cores are required (found %d).', [MinCores, Cores]) + #13#10;
  end
  else if Cores < RecCores then
  begin
    WarnText := WarnText +
      Format('- CPU cores are below recommended (%d found, %d recommended).', [Cores, RecCores]) + #13#10;
  end;

  if not NetOK then
  begin
    WarnText := WarnText + '- Active internet connection could not be confirmed. Ollama/model download may fail.' + #13#10;
  end;

  ScanReport :=
    'System Scan Results' + #13#10 + #13#10 +
    Format('Windows version: %d.%d (build %d)', [Version.Major, Version.Minor, Version.Build]) + #13#10 +
    Format('Disk free (%s): %d GB', [DiskPath, DiskGB]) + #13#10 +
    Format('RAM: %d GB', [RamGB]) + #13#10 +
    Format('CPU logical cores: %d', [Cores]) + #13#10 +
    Format('Internet check (ollama.com): %s', [BoolText(NetOK)]) + #13#10 + #13#10;

  if WarnText <> '' then
    ScanReport := ScanReport + 'Warnings:' + #13#10 + WarnText + #13#10;

  if ScanPassed then
    ScanReport := ScanReport + 'Status: PASS. This system can run SPARKY.'
  else
    ScanReport := ScanReport + 'Status: FAIL.' + #13#10 + 'Blocking issues:' + #13#10 + ScanBlockReason;
end;

function InitializeSetup(): Boolean;
begin
  ScanRan := False;
  RunSystemScan();
  if not ScanPassed then
  begin
    MsgBox(
      'System scan failed. This machine does not meet minimum requirements for SPARKY.' + #13#10 + #13#10 +
      ScanBlockReason,
      mbCriticalError,
      MB_OK
    );
    Result := False;
    Exit;
  end;
  Result := True;
end;

procedure InitializeWizard();
begin
  PostInstallPage := CreateOutputProgressPage(
    'Setting up SPARKY runtime',
    'Downloading and configuring Python, Ollama, and models.'
  );
  ScanPage := CreateCustomPage(
    wpWelcome,
    'System Scan',
    'Installer checks if this system can run SPARKY'
  );
  ScanMemo := TMemo.Create(ScanPage);
  ScanMemo.Parent := ScanPage.Surface;
  ScanMemo.Left := ScaleX(0);
  ScanMemo.Top := ScaleY(8);
  ScanMemo.Width := ScanPage.SurfaceWidth;
  ScanMemo.Height := ScaleY(250);
  ScanMemo.ReadOnly := True;
  ScanMemo.ScrollBars := ssVertical;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ScanPage.ID then
  begin
    if not ScanPassed then
    begin
      MsgBox(
        'Cannot continue because this system does not meet SPARKY minimum requirements.' + #13#10 + #13#10 +
        ScanBlockReason,
        mbCriticalError,
        MB_OK
      );
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = ScanPage.ID then
  begin
    RunSystemScan();
    ScanMemo.Lines.Text := ScanReport;
  end;
end;

procedure UpdatePostInstallProgress();
var
  Raw, StatusText, DetailText, DownloadedMB, TotalMB: string;
  RawAnsi: AnsiString;
  PercentValue: Integer;
begin
  if (PostInstallProgressFile = '') or (not FileExists(PostInstallProgressFile)) then
    Exit;

  if not LoadStringFromFile(PostInstallProgressFile, RawAnsi) then
    Exit;
  Raw := RawAnsi;

  PercentValue := StrToIntDef(ParseValue(Raw, 'PERCENT'), 0);
  if PercentValue < 0 then
    PercentValue := 0
  else if PercentValue > 100 then
    PercentValue := 100;

  StatusText := ParseValue(Raw, 'STATUS');
  DetailText := ParseValue(Raw, 'DETAIL');
  DownloadedMB := ParseValue(Raw, 'DOWNLOADED_MB');
  TotalMB := ParseValue(Raw, 'TOTAL_MB');

  if (DownloadedMB <> '0.00') and (TotalMB <> '0.00') and (Pos(' MB / ', DetailText) = 0) then
    DetailText := DetailText + ' (' + DownloadedMB + ' MB / ' + TotalMB + ' MB)';

  if StatusText = '' then
    StatusText := 'Finalizing SPARKY runtime...';
  if DetailText = '' then
    DetailText := 'Please wait while setup finishes downloading dependencies.';

  PostInstallPage.SetText(StatusText, DetailText);
  PostInstallPage.SetProgress(PercentValue, 100);
  WizardForm.StatusLabel.Caption := StatusText;
end;

function GetPostInstallFlag(const Key: string): Boolean;
var
  Raw: AnsiString;
begin
  Result := False;
  if (PostInstallProgressFile = '') or (not FileExists(PostInstallProgressFile)) then
    Exit;
  if not LoadStringFromFile(PostInstallProgressFile, Raw) then
    Exit;
  Result := ParseValue(Raw, Key) = '1';
end;

function RunPostInstall(): Boolean;
var
  ProcessHandle: Integer;
  ProcessId: Integer;
  ExitCode: Integer;
  Params: string;
  CompletedFlag: Boolean;
  FailedFlag: Boolean;
begin
  PostInstallProgressFile := ExpandConstant('{app}\installer_progress.txt');
  DeleteFile(PostInstallProgressFile);

  Params :=
    '-NoProfile -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\installer\post_install.ps1') +
    '" -AppDir "' + ExpandConstant('{app}') + '"' +
    ' -ProgressFile "' + PostInstallProgressFile + '"';

  PostInstallPage.SetText('Preparing SPARKY runtime...', 'Starting background setup...');
  PostInstallPage.SetProgress(0, 100);
  PostInstallPage.Show;

  Result := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Params,
    '',
    SW_HIDE,
    ewNoWait,
    ProcessId
  );

  if not Result then
  begin
    PostInstallPage.Hide;
    SuppressibleMsgBox(
      'SPARKY setup could not finish prerequisite installation (Python/Ollama/dependencies/model).' + #13#10 +
      'If Ollama is not installed, install Ollama manually first and run SPARKY setup again.' + #13#10 +
      'Open installer_postinstall.log inside the install folder for details.',
      mbCriticalError,
      MB_OK,
      IDOK
    );
    Result := False;
    exit;
  end;

  ProcessHandle := OpenProcess(PROCESS_QUERY_INFORMATION or SYNCHRONIZE, False, ProcessId);
  ExitCode := STILL_ACTIVE;

  try
    while True do
    begin
      UpdatePostInstallProgress();
      CompletedFlag := GetPostInstallFlag('COMPLETED');
      FailedFlag := GetPostInstallFlag('FAILED');

      if ProcessHandle <> 0 then
      begin
        if not GetExitCodeProcess(ProcessHandle, ExitCode) then
          ExitCode := STILL_ACTIVE;
      end;

      if CompletedFlag then
      begin
        if FailedFlag then
          ExitCode := 1
        else
          ExitCode := 0;
        Break;
      end;

      if (ProcessHandle <> 0) and (ExitCode <> STILL_ACTIVE) then
        Break;
      Sleep(200);
    end;
  finally
    if ProcessHandle <> 0 then
      CloseHandle(ProcessHandle);
    UpdatePostInstallProgress();
    PostInstallPage.Hide;
  end;

  if ExitCode <> 0 then
  begin
    SuppressibleMsgBox(
      'SPARKY setup could not finish prerequisite installation (Python/Ollama/dependencies/model).' + #13#10 +
      'If Ollama is not installed, install Ollama manually first and run SPARKY setup again.' + #13#10 +
      'Open installer_postinstall.log inside the install folder for details.',
      mbCriticalError,
      MB_OK,
      IDOK
    );
    Result := False;
    exit;
  end;

  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Finalizing SPARKY runtime (Python, dependencies, Ollama, model)...';
    if not RunPostInstall() then
    begin
      Abort;
    end;
  end;
end;

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent; Tasks: launchapp
