"""
Register / unregister Windows Task Scheduler logon task for the frozen .exe build.

Two registration strategies are tried in order so a single failing path does
not leave the user without autostart:

  A) PowerShell + ScheduledTasks module (Register-ScheduledTask)
  B) schtasks.exe /Create /XML with hand-rolled task XML

After either, schtasks.exe /Query verifies the task actually exists.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .runtime_support import PROJECT_ROOT, autostart_log

TASK_NAME = "VictusMorningBriefing"
# Created by Inno installer when user opts out of "run at sign-in" so the app does not re-register the task.
INSTALLER_OPT_OUT_FLAG = "VictusNoLogonAutostart.txt"
_CREATE_FLAGS = 0x08000000 if sys.platform == "win32" else 0


def install_directory() -> Path:
    return PROJECT_ROOT.resolve()


def _run(cmd: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_CREATE_FLAGS,
    )


def is_logon_task_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = _run(["schtasks", "/Query", "/TN", TASK_NAME], timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _user_id() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME", "")
    computer = os.environ.get("COMPUTERNAME", "")
    if domain and domain != computer:
        return f"{domain}\\{user}"
    return user


def _try_register_via_powershell(install_dir: Path, delay_seconds: int) -> tuple[bool, str]:
    install_dir_ps = str(install_dir.resolve())
    user_id = _user_id()
    user = os.environ.get("USERNAME", "")
    script = f"""
$ErrorActionPreference = "Stop"
$taskName = "{TASK_NAME}"
$installDir = @'
{install_dir_ps}
'@.Trim()
$exe = Join-Path $installDir 'VictusMorningBriefing.exe'
$action = New-ScheduledTaskAction -Execute $exe -Argument '--autostart' -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User '{user}'
$trigger.Delay = "PT{delay_seconds}S"
$principal = New-ScheduledTaskPrincipal -UserId '{user_id}' -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
"""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8-sig"
        ) as tmp:
            tmp.write(script)
            path = tmp.name
        r = _run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            timeout=120,
        )
        try:
            os.unlink(path)
        except OSError:
            pass
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            return False, err or f"exit {r.returncode}"
        return True, ""
    except Exception as e:
        return False, str(e)


def _try_register_via_schtasks_xml(install_dir: Path, delay_seconds: int) -> tuple[bool, str]:
    """Fallback: write a Task Scheduler XML file and import via schtasks.exe.

    Avoids the ScheduledTasks PowerShell module entirely, which helps when
    AV / policy software intercepts module loading.
    """
    from xml.sax.saxutils import escape

    exe = (install_dir / "VictusMorningBriefing.exe").resolve()
    user_id = _user_id()
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{now_iso}</Date>
    <Author>{escape(user_id)}</Author>
    <Description>Launches Victus Voice Assistant after the user signs in.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escape(user_id)}</UserId>
      <Delay>PT{int(delay_seconds)}S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user_id)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(exe))}</Command>
      <Arguments>--autostart</Arguments>
      <WorkingDirectory>{escape(str(install_dir.resolve()))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""
    fd, path = tempfile.mkstemp(suffix=".xml", prefix="VictusLogonTask_")
    os.close(fd)
    try:
        # Task Scheduler XML must be UTF-16 (LE) with BOM.
        with open(path, "w", encoding="utf-16") as f:
            f.write(xml)
        r = _run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", path, "/F"],
            timeout=60,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            return False, err or f"schtasks exit {r.returncode}"
        return True, ""
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def register_logon_task(*, delay_seconds: int = 45) -> tuple[bool, str]:
    """Register the logon task. Tries PowerShell first, then schtasks.exe /XML.

    Returns (True, "") on success — meaning the task is verified present in
    Task Scheduler, not just that one of the registration commands returned 0.
    """
    if sys.platform != "win32":
        return False, "Windows only"

    install_dir = install_directory()
    exe = install_dir / "VictusMorningBriefing.exe"
    if not exe.exists():
        return False, f"VictusMorningBriefing.exe not found in {install_dir}"

    delay_seconds = max(0, min(int(delay_seconds), 600))
    errors: list[str] = []

    ok_a, err_a = _try_register_via_powershell(install_dir, delay_seconds)
    if not ok_a:
        errors.append(f"powershell: {err_a}")
    if is_logon_task_registered():
        autostart_log("windows logon task registered (powershell)")
        return True, ""

    ok_b, err_b = _try_register_via_schtasks_xml(install_dir, delay_seconds)
    if not ok_b:
        errors.append(f"schtasks-xml: {err_b}")
    if is_logon_task_registered():
        autostart_log("windows logon task registered (schtasks /XML)")
        return True, ""

    autostart_log(f"logon task registration failed: {' | '.join(errors)}")
    return False, " | ".join(errors) or "registration failed"


def unregister_logon_task() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Windows only"
    try:
        # Try both paths; either is sufficient.
        _run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue",
            ],
            timeout=60,
        )
        _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=60)
        autostart_log("windows logon task removed")
        return True, ""
    except Exception as e:
        return False, str(e)


def _installer_opted_out_of_logon_autostart() -> bool:
    return (install_directory() / INSTALLER_OPT_OUT_FLAG).is_file()


def ensure_logon_task_if_configured(cfg: dict) -> None:
    """
    If running as frozen exe on Windows and config requests autostart but task is missing, register it.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    if _installer_opted_out_of_logon_autostart():
        return
    if not bool(cfg.get("windows_logon_autostart", True)):
        return
    if is_logon_task_registered():
        return
    delay = cfg.get("logon_task_delay_seconds", 45)
    try:
        delay_i = int(float(delay))
    except (TypeError, ValueError):
        delay_i = 45
    ok, msg = register_logon_task(delay_seconds=delay_i)
    if not ok:
        autostart_log(f"logon task ensure failed: {msg}")
