; Inno Setup 6 — https://jrsoftware.org/isinfo.php
; Build the .exe first (build_windows.ps1), then compile with ISCC.exe
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\VictusSetup.iss
;
; Post-install:
;   - seeds config.json from the bundled template if it does not exist
;   - registers a Windows sign-in task IF the user kept the autostart checkbox
;   - launches the setup wizard so the end user can pick city / voice / name

#define MyAppName "Victus Voice Assistant"
#define MyAppExeName "VictusMorningBriefing.exe"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Victus"
#define MyAppURL "https://github.com/rudraksh2611/Victus"

[Setup]
AppId={{A7B3E9D2-4C1F-4A8B-9E6D-2F1A8B3C9D4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} setup
VersionInfoProductName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (C) 2026 {#MyAppPublisher}
AppContact={#MyAppURL}
AppComments=Daily voice briefing for Windows — weather, headlines, and a friendly greeting at sign-in.
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
MinVersion=10.0
CloseApplications=force
RestartApplications=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
InfoBeforeFile=WizardBefore.txt
InfoAfterFile=INSTALL_README.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.WelcomeLabel2=This setup installs Victus Voice Assistant. After files are copied, you can choose to start it automatically when you sign in to Windows, and open the settings wizard to pick your city, voice, and name.
english.StatusRegisterTask=Setting up Windows sign-in autostart…
english.StatusSeedConfig=Preparing default settings…

[Tasks]
Name: "autostartlogon"; Description: "Start Victus automatically when I sign in to Windows"; GroupDescription: "Startup options:"
Name: "runsetupnow";    Description: "Open the settings wizard now (pick city, voice, and your name)"; GroupDescription: "After setup:"
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\launch_exe_at_logon.cmd"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\dist\config.example.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "register_logon_task_install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "INSTALL_README.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "WindowsIntegrationGuide.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Run briefing now";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Change settings";           Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"
Name: "{group}\Enable autostart at sign-in"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_logon_task_install.ps1"" -InstallDir ""{app}"" -Action Register"; Comment: "Re-create the Windows sign-in task if it ever goes missing."
Name: "{group}\Disable autostart at sign-in"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_logon_task_install.ps1"" -InstallDir ""{app}"" -Action Unregister"; Comment: "Remove the Windows sign-in task."
Name: "{group}\Windows integration guide"; Filename: "{sys}\notepad.exe"; Parameters: """{app}\WindowsIntegrationGuide.txt"""
Name: "{group}\Open install folder";       Filename: "{sys}\explorer.exe"; Parameters: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 1) Open the settings wizard (only if the user kept the "Open settings now"
;    checkbox). Wait for the wizard to close before the briefing kicks in so
;    the user's saved city / voice / name take effect on the very first run.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"; Description: "Open the settings wizard"; Flags: postinstall skipifsilent waituntilterminated; Tasks: runsetupnow

; 2) Play the first briefing immediately after install (always offered as a
;    checkbox on the Finish page). Subsequent runs are handled by the
;    Windows sign-in scheduled task that step (b) in [Code] registered.
Filename: "{app}\{#MyAppExeName}"; Description: "Run briefing now"; Flags: postinstall skipifsilent nowait

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_logon_task_install.ps1"" -InstallDir ""{app}"" -Action Uninstall"; RunOnceId: "VictusRemoveLogonTask"; Flags: runhidden

[Code]
function TaskRegistered(): Boolean;
var
  ResultCode: Integer;
begin
  // schtasks /Query exit code is 0 only when the named task exists.
  Result := Exec(
    ExpandConstant('{sys}\schtasks.exe'),
    '/Query /TN "VictusMorningBriefing"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppPath: String;
  Ps1: String;
  Params: String;
  ExampleCfg: String;
  UserCfg: String;
  Action: String;
  WantsAutostart: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    AppPath := ExpandConstant('{app}');

    // (a) Seed a working config.json from the template so the assistant runs
    //     out of the box. Existing user config is preserved on upgrade.
    ExampleCfg := AppPath + '\config.example.json';
    UserCfg := AppPath + '\config.json';
    if FileExists(ExampleCfg) and (not FileExists(UserCfg)) then
      CopyFile(ExampleCfg, UserCfg, False);

    // (b) Register or remove the Windows sign-in task based on the user's
    //     choice in [Tasks]. The PS1 script tries Register-ScheduledTask
    //     first, then falls back to schtasks.exe with hand-rolled XML, and
    //     exits non-zero if both strategies fail to leave a registered task.
    WantsAutostart := WizardIsTaskSelected('autostartlogon');
    if WantsAutostart then
      Action := 'Register'
    else
      Action := 'Unregister';

    Ps1 := AppPath + '\register_logon_task_install.ps1';
    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + Ps1 +
              '" -InstallDir "' + AppPath + '" -Action ' + Action;
    Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // (c) Verify with schtasks.exe (independent of PowerShell). If the user
    //     wanted autostart and the task is missing, surface a clear warning
    //     instead of failing silently — and tell them how to recover.
    if WantsAutostart and (not TaskRegistered()) then
    begin
      // Try one more time directly via schtasks.exe (PS may have been blocked).
      Exec('powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + Ps1 +
        '" -InstallDir "' + AppPath + '" -Action Register',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    if WantsAutostart and (not TaskRegistered()) then
    begin
      MsgBox(
        'Victus Voice Assistant was installed, but Windows blocked the' #13#10 +
        'sign-in autostart task. The app still works manually.' #13#10 #13#10 +
        'To enable autostart later, open:' #13#10 +
        '  Start menu  ->  Victus Voice Assistant  ->  Enable autostart at sign-in' #13#10 #13#10 +
        'If that also fails, your IT policy may prevent user-created tasks.',
        mbInformation, MB_OK
      );
    end;
  end;
end;
