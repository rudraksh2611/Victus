"""
Register / unregister Windows Task Scheduler logon task for the frozen .exe build.

Uses the same task name as setup_login_task.ps1 so the Python and exe flows share one slot.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .runtime_support import PROJECT_ROOT, autostart_log

TASK_NAME = "VictusMorningBriefing"

_CREATE_FLAGS = 0x08000000 if sys.platform == "win32" else 0


def install_directory() -> Path:
    return PROJECT_ROOT.resolve()


def is_logon_task_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_CREATE_FLAGS,
        )
        return r.returncode == 0
    except Exception:
        return False


def register_logon_task(*, delay_seconds: int = 45) -> tuple[bool, str]:
    """Create / overwrite the logon task pointing at launch_exe_at_logon.cmd or the exe."""
    if sys.platform != "win32":
        return False, "Windows only"

    install_dir = install_directory()
    launcher = install_dir / "launch_exe_at_logon.cmd"
    exe = install_dir / "VictusMorningBriefing.exe"

    if not launcher.exists() and not exe.exists():
        return False, f"No VictusMorningBriefing.exe (or launch_exe_at_logon.cmd) in {install_dir}"

    delay_seconds = max(0, min(int(delay_seconds), 600))
    install_dir_ps = str(install_dir.resolve())

    if launcher.exists():
        action_block = """
$installDir = @'
%s
'@.Trim()
$launcher = Join-Path $installDir 'launch_exe_at_logon.cmd'
$action = New-ScheduledTaskAction -Execute $launcher -WorkingDirectory $installDir
""" % (
            install_dir_ps,
        )
    else:
        action_block = """
$installDir = @'
%s
'@.Trim()
$exe = Join-Path $installDir 'VictusMorningBriefing.exe'
$arg = "/c set `"VICTUS_AUTOSTART=1`" && cd /d `"$installDir`" && `"$exe`""
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $arg
""" % (
            install_dir_ps,
        )

    script = (
        """
$ErrorActionPreference = "Stop"
$taskName = "%s"
"""
        % (TASK_NAME,)
        + action_block.strip()
        + """
$userId = if ($env:USERDOMAIN -and $env:USERDOMAIN -ne $env:COMPUTERNAME) {
    "$env:USERDOMAIN\\$env:USERNAME"
} else {
    $env:USERNAME
}
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT%sS"
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
"""
        % (delay_seconds,)
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ps1",
            delete=False,
            encoding="utf-8-sig",
        ) as tmp:
            tmp.write(script)
            path = tmp.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_CREATE_FLAGS,
        )
        try:
            os.unlink(path)
        except OSError:
            pass
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            return False, err or f"exit {r.returncode}"
        autostart_log("windows logon task registered")
        return True, ""
    except Exception as e:
        return False, str(e)


def unregister_logon_task() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Windows only"
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Unregister-ScheduledTask -TaskName '%s' -Confirm:$false -ErrorAction SilentlyContinue"
                % TASK_NAME,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_CREATE_FLAGS,
        )
        autostart_log("windows logon task removed")
        return True, ""
    except Exception as e:
        return False, str(e)


def ensure_logon_task_if_configured(cfg: dict) -> None:
    """
    If running as frozen exe on Windows and config requests autostart but task is missing, register it.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
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
