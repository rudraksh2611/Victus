; Inno Setup 6 — https://jrsoftware.org/isinfo.php
; Build the .exe first (build_windows.ps1), then compile this script with ISCC.exe
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\VictusSetup.iss

#define MyAppName "Victus Voice Assistant"
#define MyAppExeName "VictusMorningBriefing.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Victus"
#define MyAppURL "https://github.com/example/victus"

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

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\launch_exe_at_logon.cmd"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\dist\config.example.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "INSTALL_README.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Change settings"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Victus Voice Assistant"; Flags: nowait postinstall skipifsilent
