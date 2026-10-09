; Inno Setup script for 好好说 · Better Voice Input.
; Build with scripts\build_installer.ps1, which passes the version from pyproject.toml.

#ifndef AppVersion
  #error AppVersion is required, e.g. ISCC /DAppVersion=0.1.0 BetterVoiceInput.iss
#endif

#define AppName "好好说"
#define AppExe "BetterVoiceInput.exe"
#define RepoUrl "https://github.com/hyt0019/better-voice-input"

[Setup]
AppId={{8C6A7C72-4900-4CAE-AC30-A85A108AA07F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=hyt0019
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Better Voice Input
VersionInfoDescription={#AppName} 安装程序
; Per-user install: no administrator prompt. Startup entry, credentials and
; settings are all per-user as well.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\BetterVoiceInput
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} · Better Voice Input
OutputDir=..\release
OutputBaseFilename=BetterVoiceInput-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "chs"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\BetterVoiceInput\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RunValue = 'BetterVoiceInput';

{ Stop only the copy installed in this folder, never other copies of the app. }
procedure StopInstalledApp();
var
  ResultCode: Integer;
  Folder: String;
begin
  Folder := ExpandConstant('{app}') + '\';
  StringChangeEx(Folder, '''', '''''', True);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -Command "Get-Process BetterVoiceInput -ErrorAction SilentlyContinue | ' +
    'Where-Object { $_.Path -and $_.Path.StartsWith(''' + Folder + ''', [System.StringComparison]::OrdinalIgnoreCase) } | ' +
    'Stop-Process -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopInstalledApp();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    StopInstalledApp();
    { Remove the login entry only when it points to this installation. }
    if RegQueryStringValue(HKCU, RunKey, RunValue, Command) and
       (Pos(Lowercase(ExpandConstant('{app}') + '\'), Lowercase(Command)) > 0) then
      RegDeleteValue(HKCU, RunKey, RunValue);
  end;
end;
