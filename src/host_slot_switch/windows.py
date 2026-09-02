from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .errors import DesktopIntegrationError, MxEasySwitchError

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "HostSlotSwitch"
STOP_EVENT = r"Local\HostSlotSwitchStop_v1"
HOTKEY_MUTEX = r"Local\HostSlotSwitchHotkeys_v1"
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
WAIT_TIMEOUT = 0x102
INFINITE = 0xFFFFFFFF
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


@dataclass(frozen=True)
class WindowsHotkeyBinding:
    profile: str
    slot: int
    accelerator: str
    modifiers: int
    virtual_key: int


def parse_windows_hotkey(value: str) -> tuple[int, int]:
    aliases = {
        "alt": MOD_ALT,
        "control": MOD_CONTROL,
        "ctrl": MOD_CONTROL,
        "primary": MOD_CONTROL,
        "shift": MOD_SHIFT,
        "super": MOD_WIN,
        "win": MOD_WIN,
        "windows": MOD_WIN,
    }
    tokens: list[str]
    angle_tokens = re.findall(r"<([^<>]+)>", value)
    if angle_tokens:
        prefix = "".join(f"<{token}>" for token in angle_tokens)
        if not value.startswith(prefix):
            raise DesktopIntegrationError(f"Invalid Windows hotkey: {value!r}")
        tokens = [*angle_tokens, value[len(prefix) :]]
    else:
        tokens = [token.strip() for token in value.split("+")]
    if len(tokens) < 2 or any(not token for token in tokens):
        raise DesktopIntegrationError(f"Invalid Windows hotkey: {value!r}")

    modifiers = 0
    for token in tokens[:-1]:
        flag = aliases.get(token.casefold())
        if flag is None or modifiers & flag:
            raise DesktopIntegrationError(
                f"Unsupported or duplicate Windows hotkey modifier: {token!r}"
            )
        modifiers |= flag
    if not modifiers & (MOD_ALT | MOD_CONTROL | MOD_WIN):
        raise DesktopIntegrationError(
            f"Windows hotkey must include Ctrl, Alt, or Win: {value!r}"
        )
    return modifiers | MOD_NOREPEAT, _virtual_key(tokens[-1], value)


def _virtual_key(key: str, original: str) -> int:
    normalized = key.casefold().replace("_", "")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    function = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", normalized)
    if function:
        number = int(function.group(1))
        if number == 12:
            raise DesktopIntegrationError("F12 is reserved by Windows debuggers.")
        return 0x6F + number
    named = {
        "space": 0x20,
        "tab": 0x09,
        "escape": 0x1B,
        "return": 0x0D,
        "enter": 0x0D,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "insert": 0x2D,
        "delete": 0x2E,
        "backspace": 0x08,
    }
    try:
        return named[normalized]
    except KeyError as exc:
        raise DesktopIntegrationError(f"Invalid Windows hotkey: {original!r}") from exc


def build_windows_bindings(config: Config) -> list[WindowsHotkeyBinding]:
    bindings: list[WindowsHotkeyBinding] = []
    seen: set[tuple[int, int]] = set()
    slots: set[int] = set()
    for profile in config.profiles.values():
        if not profile.hotkey:
            continue
        modifiers, virtual_key = parse_windows_hotkey(profile.hotkey)
        combination = (modifiers, virtual_key)
        if combination in seen:
            raise DesktopIntegrationError(f"Duplicate hotkey: {profile.hotkey}")
        if profile.slot in slots:
            raise DesktopIntegrationError(
                "Only one Windows hotkey can be assigned to each Easy-Switch slot."
            )
        seen.add(combination)
        slots.add(profile.slot)
        bindings.append(
            WindowsHotkeyBinding(
                profile.name,
                profile.slot,
                profile.hotkey,
                modifiers,
                virtual_key,
            )
        )
    if not bindings:
        raise DesktopIntegrationError(
            "No profiles have a 'hotkey' value in the config."
        )
    return bindings


def windows_startup_command(
    *,
    config_path: Path,
    device: str | None = None,
    hid_path: str | None = None,
) -> list[str]:
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    command = [
        str(executable.resolve()),
        "-m",
        "host_slot_switch",
        f"--config={config_path.expanduser().resolve()}",
    ]
    if device:
        command.append(f"--device={device}")
    if hid_path:
        command.append(f"--hid-path={hid_path}")
    command.extend(["hotkeys", "run"])
    return command


def install_windows_hotkeys(
    config: Config,
    *,
    command: Sequence[str],
    dry_run: bool = False,
) -> list[WindowsHotkeyBinding]:
    _ensure_windows()
    bindings = build_windows_bindings(config)
    if dry_run:
        return bindings
    import winreg

    _signal_stop()
    _check_hotkeys_available(bindings)
    serialized = subprocess.list2cmdline(list(command))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, serialized)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    try:
        subprocess.Popen(
            list(command),
            close_fds=True,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise DesktopIntegrationError(
            f"The startup command was saved, but the hotkey listener could not start: {exc}"
        ) from exc
    return bindings


def uninstall_windows_hotkeys(*, dry_run: bool = False) -> list[str]:
    _ensure_windows()
    target = rf"HKCU\{RUN_KEY}\{RUN_VALUE}"
    if dry_run:
        return [target]
    import winreg

    removed = True
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except FileNotFoundError:
        removed = False
    _signal_stop()
    return [target] if removed else []


def run_windows_hotkeys(
    config: Config,
    switch: Callable[[int], None],
) -> None:
    _ensure_windows()
    bindings = build_windows_bindings(config)
    kernel32, user32 = _win_apis()
    mutex = kernel32.CreateMutexW(None, False, HOTKEY_MUTEX)
    if not mutex:
        raise DesktopIntegrationError("Windows could not create the hotkey mutex.")
    acquired = False
    event = None
    registered: list[int] = []
    try:
        wait = kernel32.WaitForSingleObject(mutex, 5000)
        if wait not in {WAIT_OBJECT_0, WAIT_ABANDONED}:
            raise DesktopIntegrationError(
                "The Windows hotkey listener is already running."
            )
        acquired = True
        event = kernel32.CreateEventW(None, False, False, STOP_EVENT)
        if not event:
            raise DesktopIntegrationError("Windows could not create the stop event.")
        for identifier, binding in enumerate(bindings, 1):
            if not user32.RegisterHotKey(
                None, identifier, binding.modifiers, binding.virtual_key
            ):
                error = ctypes.get_last_error()
                raise DesktopIntegrationError(
                    f"Windows could not register {binding.accelerator!r} "
                    f"(error {error}); another app may already use it."
                )
            registered.append(identifier)

        handles = (wintypes.HANDLE * 1)(event)
        message = wintypes.MSG()
        by_id = {identifier: binding for identifier, binding in enumerate(bindings, 1)}
        while True:
            result = user32.MsgWaitForMultipleObjects(
                1, handles, False, INFINITE, QS_ALLINPUT
            )
            if result == WAIT_OBJECT_0:
                break
            if result != WAIT_OBJECT_0 + 1:
                raise DesktopIntegrationError(
                    f"Windows hotkey message loop failed (result {result})."
                )
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                if message.message == WM_HOTKEY and message.wParam in by_id:
                    binding = by_id[message.wParam]
                    try:
                        switch(binding.slot)
                    except MxEasySwitchError as exc:
                        _write_listener_log(str(exc))
    finally:
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)
        if event:
            kernel32.CloseHandle(event)
        if acquired:
            kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


def _signal_stop() -> None:
    kernel32, _ = _win_apis()
    event = kernel32.OpenEventW(0x0002, False, STOP_EVENT)
    if event:
        try:
            kernel32.SetEvent(event)
        finally:
            kernel32.CloseHandle(event)


def _check_hotkeys_available(bindings: Sequence[WindowsHotkeyBinding]) -> None:
    _, user32 = _win_apis()
    deadline = time.monotonic() + 3
    while True:
        registered: list[int] = []
        failed: WindowsHotkeyBinding | None = None
        failure_code = 0
        for identifier, binding in enumerate(bindings, 1):
            if user32.RegisterHotKey(
                None, identifier, binding.modifiers, binding.virtual_key
            ):
                registered.append(identifier)
            else:
                failed = binding
                failure_code = ctypes.get_last_error()
                break
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)
        if failed is None:
            return
        if time.monotonic() >= deadline:
            raise DesktopIntegrationError(
                f"Windows could not register {failed.accelerator!r} "
                f"(error {failure_code}); "
                "another app may already use it."
            )
        time.sleep(0.1)


def _write_listener_log(message: str) -> None:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HostSlotSwitch"
    try:
        base.mkdir(parents=True, exist_ok=True)
        with (base / "hotkeys.log").open("a", encoding="utf-8") as stream:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            stream.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def _ensure_windows() -> None:
    if os.name != "nt":
        raise DesktopIntegrationError(
            "Windows hotkey management is available only on Windows."
        )


def _win_apis():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CreateEventW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    user32.RegisterHotKey.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.MsgWaitForMultipleObjects.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    return kernel32, user32
