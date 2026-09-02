from __future__ import annotations

import ast
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .errors import DesktopIntegrationError

MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
CUSTOM_KEY = "custom-keybindings"
PATH_PREFIX = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
OWN_PATH_PREFIX = PATH_PREFIX + "host-slot-switch-"
OWN_PATHS = tuple(f"{OWN_PATH_PREFIX}slot-{slot}/" for slot in range(1, 4))

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class HotkeyBinding:
    profile: str
    slot: int
    accelerator: str
    path: str
    command: str


class GSettings:
    def __init__(
        self,
        executable: str | None = None,
        *,
        runner: Runner = subprocess.run,
        timeout: float = 5.0,
    ) -> None:
        self.executable = executable or shutil.which("gsettings") or ""
        self.runner = runner
        self.timeout = timeout

    def ensure_available(self) -> None:
        if not self.executable:
            raise DesktopIntegrationError(
                "gsettings was not found; GNOME hotkeys cannot be managed."
            )

    def get(self, schema: str, key: str, path: str | None = None) -> str:
        target = f"{schema}:{path}" if path else schema
        return self._run(["get", target, key]).strip()

    def set(self, schema: str, key: str, value: str, path: str | None = None) -> None:
        target = f"{schema}:{path}" if path else schema
        self._run(["set", target, key, value])

    def set_string(
        self, schema: str, key: str, value: str, path: str | None = None
    ) -> None:
        # GVariant accepts JSON-style quoted UTF-8 strings. Keep non-BMP text as
        # UTF-8 because GLib does not accept JSON surrogate-pair escapes here.
        self.set(schema, key, json.dumps(value, ensure_ascii=False), path)

    def reset_recursively(self, schema: str, path: str) -> None:
        self._run(["reset-recursively", f"{schema}:{path}"])

    def _run(self, args: Sequence[str]) -> str:
        self.ensure_available()
        try:
            completed = self.runner(
                [self.executable, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise DesktopIntegrationError(
                f"gsettings executable not found: {self.executable}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DesktopIntegrationError(
                f"gsettings did not respond within {self.timeout:g} seconds."
            ) from exc
        except (OSError, ValueError) as exc:
            raise DesktopIntegrationError(f"gsettings could not run: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise DesktopIntegrationError(
                f"gsettings failed: {detail or 'unknown error'}"
            )
        return completed.stdout


def parse_string_array(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("@as "):
        value = value[4:].strip()
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise DesktopIntegrationError(
            f"Unexpected gsettings array value: {value!r}"
        ) from exc
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise DesktopIntegrationError(f"Unexpected gsettings array value: {value!r}")
    return parsed


def parse_string(value: str) -> str:
    value = value.strip()
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise DesktopIntegrationError(
            f"Unexpected gsettings string value: {value!r}"
        ) from exc
    if not isinstance(parsed, str):
        raise DesktopIntegrationError(f"Unexpected gsettings string value: {value!r}")
    return parsed


def ensure_gnome_desktop(environ: Mapping[str, str] | None = None) -> None:
    environ = os.environ if environ is None else environ
    current_desktop = environ.get("XDG_CURRENT_DESKTOP", "").strip()
    desktop_session = environ.get("DESKTOP_SESSION", "").strip()

    # XDG_CURRENT_DESKTOP is a colon-separated list and is the authoritative
    # desktop identity when present. DESKTOP_SESSION is only a legacy fallback.
    detected = current_desktop or desktop_session
    tokens = [
        token.strip().casefold()
        for token in re.split(r"[:;]", detected)
        if token.strip()
    ]
    if any(token == "gnome" or token.startswith("gnome-") for token in tokens):
        return

    detail = detected or "unknown"
    raise DesktopIntegrationError(
        "GNOME hotkey installation is only supported in a GNOME desktop "
        f"session (detected: {detail!r}). Configure an equivalent shortcut "
        "manually in your current desktop environment."
    )


def ensure_no_accelerator_conflicts(
    bindings: Sequence[HotkeyBinding],
    current_paths: Sequence[str],
    settings: GSettings,
) -> None:
    requested = {
        canonical_accelerator(binding.accelerator): binding for binding in bindings
    }
    for path in current_paths:
        if path in OWN_PATHS:
            continue
        raw_value = settings.get(CUSTOM_SCHEMA, "binding", path)
        existing = parse_string(raw_value)
        if not existing:
            continue
        try:
            canonical = canonical_accelerator(existing)
        except DesktopIntegrationError:
            # GNOME accepts more key names than this tool intentionally permits.
            # An accelerator outside our conservative grammar cannot collide with
            # one that build_bindings() accepted.
            continue
        binding = requested.get(canonical)
        if binding is not None:
            raise DesktopIntegrationError(
                "An existing GNOME custom shortcut already uses the requested "
                f"hotkey {binding.accelerator!r}: {path}"
            )


def build_bindings(
    config: Config,
    *,
    cli_command: Sequence[str] | None = None,
) -> list[HotkeyBinding]:
    cli_command = tuple(cli_command or discover_cli_command())
    bindings: list[HotkeyBinding] = []
    seen_accelerators: set[tuple[tuple[str, ...], str]] = set()
    seen_paths: set[str] = set()
    for profile in config.profiles.values():
        if not profile.hotkey:
            continue
        accelerator = normalize_accelerator(profile.hotkey)
        canonical_hotkey = canonical_accelerator(accelerator)
        if canonical_hotkey in seen_accelerators:
            raise DesktopIntegrationError(f"Duplicate hotkey in config: {accelerator}")
        seen_accelerators.add(canonical_hotkey)
        path = OWN_PATHS[profile.slot - 1]
        if path in seen_paths:
            raise DesktopIntegrationError(
                "Only one GNOME hotkey can be assigned to each Easy-Switch slot."
            )
        seen_paths.add(path)
        command = shlex.join([*cli_command, "switch", "--", str(profile.slot)])
        bindings.append(
            HotkeyBinding(
                profile.name,
                profile.slot,
                accelerator,
                path,
                command,
            )
        )
    if not bindings:
        raise DesktopIntegrationError(
            "No profiles have a 'hotkey' value in the config."
        )
    return bindings


def discover_cli_command() -> list[str]:
    candidates = [Path(sys.argv[0]).expanduser()]
    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [executable_dir / "host-slot-switch", executable_dir / "host-slot-switch.exe"]
    )
    unsafe_permissions: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            info = resolved.stat()
        except OSError:
            continue
        if not resolved.name.lower().startswith("host-slot-switch"):
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if os.name == "posix":
            if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                unsafe_permissions.append(resolved)
                continue
            if not os.access(resolved, os.X_OK) or (
                hasattr(os, "getuid") and info.st_uid not in {0, os.getuid()}
            ):
                continue
        return [str(resolved)]
    if unsafe_permissions:
        rejected = unsafe_permissions[0]
        raise DesktopIntegrationError(
            f"The installed entry point is writable by group or others: {rejected}. "
            f"Run 'chmod go-w {shlex.quote(str(rejected))}' and retry."
        )
    raise DesktopIntegrationError(
        "Cannot find the installed host-slot-switch entry point. Install the package "
        "before registering persistent hotkeys."
    )


def canonical_accelerator(value: str) -> tuple[tuple[str, ...], str]:
    aliases = {
        "control": "control",
        "ctrl": "control",
        "primary": "control",
        "shift": "shift",
        "alt": "alt",
        "super": "super",
    }
    modifiers: list[str] = []
    offset = 0
    while match := re.match(r"<([^<>]+)>", value[offset:]):
        token = match.group(1).casefold()
        if token not in aliases:
            raise DesktopIntegrationError(
                f"Unsupported GNOME hotkey modifier: <{token}>"
            )
        modifier = aliases[token]
        if modifier in modifiers:
            raise DesktopIntegrationError(f"Duplicate GNOME hotkey modifier: <{token}>")
        modifiers.append(modifier)
        offset += match.end()
    key = value[offset:]
    if not key or any(character.isspace() or character in "<>" for character in key):
        raise DesktopIntegrationError(f"Invalid GNOME hotkey: {value!r}")
    named_keys = {
        "space",
        "tab",
        "escape",
        "return",
        "home",
        "end",
        "page_up",
        "page_down",
        "left",
        "right",
        "up",
        "down",
        "insert",
        "delete",
        "backspace",
        "kp_add",
        "kp_subtract",
        "kp_multiply",
        "kp_divide",
        "kp_enter",
    }
    valid_key = (
        (len(key) == 1 and key.isascii() and key.isalnum())
        or bool(re.fullmatch(r"F(?:[1-9]|[12][0-9]|3[0-5])", key, re.IGNORECASE))
        or bool(re.fullmatch(r"KP_[0-9]", key, re.IGNORECASE))
        or key.casefold() in named_keys
    )
    if (
        not valid_key
        or not modifiers
        or not {"control", "alt", "super"}.intersection(modifiers)
    ):
        raise DesktopIntegrationError(f"Invalid or unsafe GNOME hotkey: {value!r}")
    return tuple(sorted(modifiers)), key.casefold()


def normalize_accelerator(value: str) -> str:
    if value.startswith("<") or "+" not in value:
        return value
    aliases = {
        "control": "Control",
        "ctrl": "Control",
        "primary": "Control",
        "shift": "Shift",
        "alt": "Alt",
        "super": "Super",
        "win": "Super",
        "windows": "Super",
    }
    tokens = [token.strip() for token in value.split("+")]
    if len(tokens) < 2 or any(not token for token in tokens):
        raise DesktopIntegrationError(f"Invalid GNOME hotkey: {value!r}")
    modifiers: list[str] = []
    for token in tokens[:-1]:
        try:
            modifiers.append(f"<{aliases[token.casefold()]}>")
        except KeyError as exc:
            raise DesktopIntegrationError(
                f"Unsupported GNOME hotkey modifier: {token!r}"
            ) from exc
    return "".join(modifiers) + tokens[-1]


def install_hotkeys(
    config: Config,
    settings: GSettings,
    *,
    cli_command: Sequence[str] | None = None,
    dry_run: bool = False,
) -> list[HotkeyBinding]:
    ensure_gnome_desktop()
    bindings = build_bindings(config, cli_command=cli_command)
    current = parse_string_array(settings.get(MEDIA_SCHEMA, CUSTOM_KEY))
    ensure_no_accelerator_conflicts(bindings, current, settings)
    desired_paths = [binding.path for binding in bindings]
    stale_paths = [
        path for path in current if path in OWN_PATHS and path not in desired_paths
    ]

    if dry_run:
        return bindings

    for binding in bindings:
        settings.set_string(
            CUSTOM_SCHEMA, "name", f"Host Slot Switch: {binding.profile}", binding.path
        )
        settings.set_string(CUSTOM_SCHEMA, "command", binding.command, binding.path)
        settings.set_string(CUSTOM_SCHEMA, "binding", binding.accelerator, binding.path)
    latest = parse_string_array(settings.get(MEDIA_SCHEMA, CUSTOM_KEY))
    merged = [path for path in latest if path not in OWN_PATHS]
    merged.extend(desired_paths)
    settings.set(MEDIA_SCHEMA, CUSTOM_KEY, repr(merged))
    installed = parse_string_array(settings.get(MEDIA_SCHEMA, CUSTOM_KEY))
    unrelated = [path for path in latest if path not in OWN_PATHS]
    if not all(path in installed for path in [*unrelated, *desired_paths]):
        raise DesktopIntegrationError(
            "GNOME did not retain the complete custom-shortcut list."
        )
    for path in stale_paths:
        settings.reset_recursively(CUSTOM_SCHEMA, path)
    return bindings


def uninstall_hotkeys(settings: GSettings, *, dry_run: bool = False) -> list[str]:
    current = parse_string_array(settings.get(MEDIA_SCHEMA, CUSTOM_KEY))
    owned = [path for path in current if path in OWN_PATHS]
    kept = [path for path in current if path not in OWN_PATHS]
    if dry_run:
        return owned
    settings.set(MEDIA_SCHEMA, CUSTOM_KEY, repr(kept))
    remaining = parse_string_array(settings.get(MEDIA_SCHEMA, CUSTOM_KEY))
    if any(path in remaining for path in owned) or not all(
        path in remaining for path in kept
    ):
        raise DesktopIntegrationError(
            "GNOME did not retain the expected custom-shortcut list."
        )
    for path in owned:
        settings.reset_recursively(CUSTOM_SCHEMA, path)
    return owned
