"""Manage this app's current-user Windows login entry."""

from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

from .settings import Settings, project_root

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BetterVoiceInput"


class StartupError(OSError):
    pass


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        arguments = [sys.executable, "--background"]
    else:
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        arguments = [
            str(pythonw if pythonw.is_file() else python),
            str(project_root() / "scripts" / "run_app.py"),
            "--background",
        ]
    return subprocess.list2cmdline(arguments)


def read_entry() -> tuple[object, int] | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError:
        raise StartupError("无法读取开机自启动设置，请检查当前用户权限。") from None


def startup_enabled() -> bool:
    entry = read_entry()
    return bool(entry and entry[1] in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and entry[0])


def write_entry(entry: tuple[object, int] | None) -> None:
    try:
        if entry is None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        else:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, entry[1], entry[0])
    except OSError:
        raise StartupError("无法修改开机自启动设置，请检查当前用户权限后重试。") from None


def save_settings_with_startup(settings: Settings, path: Path | None = None) -> None:
    previous = read_entry()
    desired = (startup_command(), winreg.REG_SZ) if settings.start_on_login else None
    changed = previous != desired
    if changed:
        write_entry(desired)
    try:
        settings.save(path)
    except OSError:
        if changed:
            try:
                write_entry(previous)
            except StartupError:
                raise StartupError("设置文件保存失败，且启动项未能恢复。请重新检查开机自启动选项。") from None
        raise
