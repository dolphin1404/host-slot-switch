from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .errors import DependencyError, DeviceUnavailableError

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SwitchResult:
    device: str
    slot: int
    command: tuple[str, ...]
    stdout: str = ""


@dataclass(frozen=True)
class SolaarDevice:
    number: int
    name: str
    online: bool
    serial: str | None = None
    transport: str | None = None
    supports_change_host: bool | None = None


class SolaarBackend:
    name = "solaar"

    def __init__(
        self,
        executable: str | None = None,
        *,
        runner: Runner = subprocess.run,
        timeout: float = 8.0,
        inspect_timeout: float = 20.0,
    ) -> None:
        self.executable = executable or shutil.which("solaar") or ""
        self.runner = runner
        self.timeout = timeout
        self.inspect_timeout = inspect_timeout

    def ensure_available(self) -> None:
        if not self.executable:
            raise DependencyError(
                "Solaar was not found. Install it first (for Ubuntu: sudo apt install solaar)."
            )

    def version(self) -> str | None:
        self.ensure_available()
        completed = self._run([self.executable, "--version"], check=False)
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0:
            raise DependencyError(
                f"Solaar could not start: {output or f'exit {completed.returncode}'}"
            )
        return output or None

    def list_devices(self) -> list[SolaarDevice]:
        self.ensure_available()
        # `solaar show` enumerates every feature of every online device and can
        # legitimately take several seconds per device. Keep the latency-sensitive
        # switch timeout separate from this diagnostic operation.
        completed = self._run(
            [self.executable, "show"],
            check=False,
            timeout=self.inspect_timeout,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise DeviceUnavailableError(
                f"Solaar could not inspect devices: {output.strip() or f'exit {completed.returncode}'}"
            )
        devices: list[SolaarDevice] = []
        pattern = re.compile(r"^\s{2}(\d+):\s+(.+?)\s*$")
        lines = output.splitlines()
        boundaries = sorted(
            {
                index
                for index, line in enumerate(lines)
                if pattern.match(line) or (line and line == line.lstrip())
            }
        )
        for boundary_number, index in enumerate(boundaries):
            numbered = pattern.match(lines[index])
            next_index = (
                boundaries[boundary_number + 1]
                if boundary_number + 1 < len(boundaries)
                else len(lines)
            )
            raw_block = "\n".join(lines[index + 1 : next_index])
            if numbered:
                number, name = int(numbered.group(1)), numbered.group(2)
            else:
                # Older Solaar versions display direct Bluetooth devices as a
                # top-level name rather than as a numbered receiver child.
                if not re.search(r"^\s*Kind\s*:\s*\S+", raw_block, re.MULTILINE):
                    continue
                number, name = 0, lines[index].strip()
            block = raw_block.lower()
            offline = "device is offline" in block or "online: false" in block
            serial = _field(raw_block, "Serial number") or _field(raw_block, "Unit ID")
            wpid = _field(raw_block, "WPID")
            usb_id = _field(raw_block, "USB id")
            if wpid:
                transport = f"receiver (WPID {wpid})"
            elif usb_id:
                transport = f"direct/Bluetooth HID ({usb_id})"
            else:
                transport = None
            if offline:
                supports_change_host = None
            elif "{1814}" in block:
                supports_change_host = True
            elif "supports " in block and "hid++" in block:
                supports_change_host = False
            else:
                supports_change_host = None
            devices.append(
                SolaarDevice(
                    number,
                    name,
                    not offline,
                    serial,
                    transport,
                    supports_change_host,
                )
            )
        return devices

    def switch(self, device: str, slot: int, *, dry_run: bool = False) -> SwitchResult:
        self.ensure_available()
        if slot not in range(1, 4):
            raise ValueError("slot must be between 1 and 3")
        command = (self.executable, "config", "--", device, "change-host", str(slot))
        if dry_run:
            return SwitchResult(device, slot, command)

        completed = self._run(list(command), check=False, outcome_uncertain=True)
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0:
            lowered = output.lower()
            if "no online device" in lowered:
                raise DeviceUnavailableError(
                    f"{device!r} is not connected to this computer right now. "
                    "The switch command must run on the host currently controlling the mouse."
                )
            if "no setting 'change-host'" in lowered:
                raise DeviceUnavailableError(
                    f"{device!r} does not expose the HID++ Change Host feature through Solaar."
                )
            raise DeviceUnavailableError(
                f"Solaar could not switch {device!r} to slot {slot}: {output or 'unknown error'}"
            )
        return SwitchResult(device, slot, command, output)

    def _run(
        self,
        command: Sequence[str],
        *,
        check: bool,
        timeout: float | None = None,
        outcome_uncertain: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        timeout = self.timeout if timeout is None else timeout
        try:
            return self.runner(
                list(command),
                check=check,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise DependencyError(
                f"Solaar executable not found: {self.executable}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            if not outcome_uncertain:
                raise DeviceUnavailableError(
                    f"Solaar did not respond within {timeout:g} seconds."
                ) from exc
            raise DeviceUnavailableError(
                f"Solaar did not respond within {timeout:g} seconds. The command may "
                "already have been delivered; check the destination before retrying and "
                "use the physical Easy-Switch button if the mouse is unreachable."
            ) from exc
        except (OSError, ValueError) as exc:
            raise DependencyError(f"Solaar could not run: {exc}") from exc


def _field(block: str, label: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", block, re.MULTILINE)
    value = match.group(1).strip() if match else ""
    return value or None
