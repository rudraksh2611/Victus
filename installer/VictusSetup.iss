; Inno Setup 6 — https://jrsoftware.org/isinfo.php
; Build the .exe first (build_windows.ps1), then compile this script with ISCC.exe
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\VictusSetup.iss

#define MyAppName "Victus Voice Assistant"
#define MyAppExeName "VictusMorningBriefing.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Victus"
#define MyAppURL "https://github.com/rudraksh2611/Victus"

[Setup]
AppId={{A7B3E9D2-4C1F-4A8B-9E6D-2F1A8B3C9D4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\VictusVoiceAssistant
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\Output
OutputBaseFilename=VictusVoiceAssistant_Setup
SetupIconFile=
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=no
InfoBeforeFile=
InfoAfterFile=INSTALL_README.txt
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostartlogon"; Description: "Run Victus automatically when I sign in to Windows — after each restart or new login (uses Task Scheduler; recommended)"; GroupDescription: "Startup"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\launch_exe_at_logon.cmd"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\dist\config.example.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "register_logon_task_install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "INSTALL_README.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Change settings"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"
Name: "{group}\Open install folder"; Filename: "{sys}\explorer.exe"; Parameters: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Victus Voice Assistant"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_logon_task_install.ps1"" -InstallDir ""{app}"" -Action Uninstall"; RunOnceId: "VictusRemoveLogonTask"; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppPath: String;
  Ps1: String;
  Params: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppPath := ExpandConstant('{app}');
    Ps1 := AppPath + '\register_logon_task_install.ps1';
    if WizardIsTaskSelected('autostartlogon') then
    begin
      Params := '-NoProfile -ExecutionPolicy Bypass -File "' + Ps1 + '" -InstallDir "' + AppPath + '" -Action Register';
      Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end
    else
    begin
      Params := '-NoProfile -ExecutionPolicy Bypass -File "' + Ps1 + '" -InstallDir "' + AppPath + '" -Action Unregister';
      Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
