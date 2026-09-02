from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

DEFAULT_CONFIG = {
    "device": "MX Vertical",
    "backend": "solaar",
    "profiles": {
        "laptop": {"slot": 1, "hotkey": "<Control><Shift>1"},
        "linux": {"slot": 2, "hotkey": "<Control><Shift>2"},
    },
}
MAX_CONFIG_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Profile:
    name: str
    slot: int
    hotkey: str | None = None


@dataclass(frozen=True)
class Config:
    device: str
    backend: str
    profiles: Mapping[str, Profile]

    def resolve_target(self, target: str) -> int:
        normalized = target.strip().lower()
        if normalized.isdecimal():
            slot = int(normalized)
            _validate_slot(slot, "target")
            return slot
        try:
            return self.profiles[normalized].slot
        except KeyError as exc:
            choices = ", ".join(sorted(self.profiles))
            raise ConfigurationError(
                f"Unknown target {target!r}. Use slot 1-3 or one of: {choices}."
            ) from exc


def default_config_path() -> Path:
    explicit = os.environ.get("HOST_SLOT_SWITCH_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "host-slot-switch" / "config.json"


def load_config(path: Path | None = None) -> Config:
    explicit = path is not None or bool(os.environ.get("HOST_SLOT_SWITCH_CONFIG"))
    path = path or default_config_path()
    if os.path.lexists(path):
        try:
            raw = json.loads(_read_config_text(path), object_pairs_hook=_unique_object)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Cannot read config {path}: {exc}") from exc
    elif explicit:
        raise ConfigurationError(f"Config does not exist: {path}")
    else:
        raw = DEFAULT_CONFIG
    return parse_config(raw)


def parse_config(raw: Any) -> Config:
    if not isinstance(raw, dict):
        raise ConfigurationError("Config root must be a JSON object.")
    unknown = set(raw) - {"device", "backend", "profiles"}
    if unknown:
        raise ConfigurationError(
            f"Unknown config key(s): {', '.join(sorted(unknown))}."
        )

    device = raw.get("device", DEFAULT_CONFIG["device"])
    backend = raw.get("backend", DEFAULT_CONFIG["backend"])
    profiles_raw = raw.get("profiles", DEFAULT_CONFIG["profiles"])

    if not isinstance(device, str) or not device.strip():
        raise ConfigurationError("'device' must be a non-empty string.")
    if backend != "solaar":
        raise ConfigurationError(
            "Only the 'solaar' backend is supported in this release."
        )
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ConfigurationError("'profiles' must be a non-empty object.")

    profiles: dict[str, Profile] = {}
    for name, value in profiles_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError("Profile names must be non-empty strings.")
        normalized = name.strip().lower()
        if normalized.isdecimal():
            raise ConfigurationError(
                f"Numeric profile names are reserved for Easy-Switch slots: {name!r}."
            )
        if normalized in profiles:
            raise ConfigurationError(f"Duplicate profile name: {normalized!r}.")
        if not isinstance(value, dict):
            raise ConfigurationError(f"Profile {name!r} must be an object.")
        unknown_profile = set(value) - {"slot", "hotkey"}
        if unknown_profile:
            raise ConfigurationError(
                f"Unknown key(s) in profile {name!r}: "
                f"{', '.join(sorted(unknown_profile))}."
            )
        slot = value.get("slot")
        _validate_slot(slot, f"profiles.{name}.slot")
        hotkey = value.get("hotkey")
        if hotkey is not None and (not isinstance(hotkey, str) or not hotkey.strip()):
            raise ConfigurationError(
                f"profiles.{name}.hotkey must be a non-empty string."
            )
        if hotkey is not None:
            hotkey = hotkey.strip()
        profiles[normalized] = Profile(normalized, slot, hotkey)

    return Config(device.strip(), backend, profiles)


def write_default_config(path: Path | None = None, *, force: bool = False) -> Path:
    path = path or default_config_path()
    payload = json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n"
    try:
        if os.path.lexists(path) and not force:
            raise ConfigurationError(
                f"Config already exists: {path} (use --force to replace it)."
            )
        _ensure_config_parent(path.parent)
        if force:
            _atomic_replace(path, payload)
        else:
            _exclusive_write(path, payload)
    except OSError as exc:
        raise ConfigurationError(f"Cannot write config {path}: {exc}") from exc
    return path


def _validate_slot(value: Any, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in range(1, 4)
    ):
        raise ConfigurationError(f"{field} must be an Easy-Switch slot from 1 to 3.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"Duplicate JSON key: {key!r}.")
        result[key] = value
    return result


def _read_config_text(path: Path) -> str:
    before = path.lstat()
    _validate_config_stat(path, before)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        current = os.fstat(fd)
        _validate_config_stat(path, current)
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            content = stream.read(MAX_CONFIG_BYTES + 1)
    finally:
        os.close(fd)
    if len(content.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ConfigurationError(
            f"Config is larger than {MAX_CONFIG_BYTES} bytes: {path}"
        )
    return content


def _validate_config_stat(path: Path, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise ConfigurationError(f"Config must not be a symbolic link: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise ConfigurationError(f"Config must be a regular file: {path}")
    if info.st_size > MAX_CONFIG_BYTES:
        raise ConfigurationError(
            f"Config is larger than {MAX_CONFIG_BYTES} bytes: {path}"
        )
    if os.name == "posix":
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ConfigurationError(
                f"Config must be owned by the current user: {path}"
            )
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError(
                f"Config must not be group/world writable (run chmod 600 {path}): {path}"
            )


def _ensure_config_parent(parent: Path) -> None:
    existed = parent.exists()
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = parent.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ConfigurationError(
            f"Config parent must be a directory, not a symlink: {parent}"
        )
    if os.name == "posix":
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ConfigurationError(
                f"Config parent must be owned by the current user: {parent}"
            )
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfigurationError(
                f"Config parent must not be group/world writable: {parent}"
            )
        if not existed:
            parent.chmod(0o700)


def _exclusive_write(path: Path, payload: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_replace(path: Path, payload: str) -> None:
    if os.path.lexists(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ConfigurationError(
                f"Refusing to replace a symlink or non-regular config: {path}"
            )
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
