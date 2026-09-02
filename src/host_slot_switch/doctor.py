from __future__ import annotations

import os
import platform
from dataclasses import asdict, dataclass

from .config import Config
from .errors import DesktopIntegrationError, MxEasySwitchError
from .gnome import ensure_gnome_desktop
from .solaar import SolaarBackend


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_checks(
    config: Config, backend: SolaarBackend, *, device: str | None = None
) -> list[Check]:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get(
        "DESKTOP_SESSION", "not reported"
    )
    try:
        ensure_gnome_desktop()
        desktop_check = Check("desktop", True, desktop)
    except DesktopIntegrationError:
        desktop_check = Check(
            "desktop",
            False,
            f"{desktop} (GNOME shortcut installer unavailable; bind commands manually)",
        )
    checks = [
        Check(
            "platform", platform.system() in {"Linux", "Darwin"}, platform.platform()
        ),
        desktop_check,
    ]
    try:
        version = backend.version()
        checks.append(Check("solaar", True, version or "available"))
    except MxEasySwitchError as exc:
        checks.append(Check("solaar", False, str(exc)))
        return checks

    try:
        devices = backend.list_devices()
        query = (device or config.device).casefold()
        matches = [
            candidate
            for candidate in devices
            if query in candidate.name.casefold()
            or (candidate.serial and query == candidate.serial.casefold())
            or query == str(candidate.number)
        ]
        if len(matches) > 1:
            names = ", ".join(candidate.name for candidate in matches)
            checks.append(Check("device", False, f"Ambiguous device selector: {names}"))
        elif matches:
            match = matches[0]
            state = "online" if match.online else "offline"
            checks.append(Check("device", match.online, f"{match.name} ({state})"))
            checks.append(
                Check("transport", bool(match.transport), match.transport or "unknown")
            )
            if match.supports_change_host is True:
                checks.append(Check("change-host", True, "HID++ feature 0x1814"))
            elif match.supports_change_host is False:
                checks.append(
                    Check("change-host", False, "HID++ feature 0x1814 not found")
                )
            else:
                checks.append(
                    Check(
                        "change-host",
                        False,
                        "cannot verify while the device is offline or feature data is unavailable",
                    )
                )
        else:
            checks.append(
                Check(
                    "device", False, f"No device matching {(device or config.device)!r}"
                )
            )
    except MxEasySwitchError as exc:
        checks.append(Check("device", False, str(exc)))
    return checks


def checks_as_dicts(checks: list[Check]) -> list[dict[str, object]]:
    return [asdict(check) for check in checks]
