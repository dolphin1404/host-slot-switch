from __future__ import annotations

import importlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import DependencyError, DeviceUnavailableError
from .solaar import SolaarDevice, SwitchResult

LOGITECH_VENDOR_ID = 0x046D
HIDPP_LONG_REPORT = 0x11
HIDPP_LONG_LENGTH = 20
SOFTWARE_ID = 0x0D
CHANGE_HOST = 0x1814
DEVICE_NAME = 0x0005
HIDPP_USAGE_PAGES = {0xFF00, 0xFF43}
HIDPP_USAGES = {0x0001, 0x0002, 0x0202}


@dataclass(frozen=True)
class NativeDevice(SolaarDevice):
    path: bytes | str = b""
    control_output: bool = False


class _ProtocolError(Exception):
    pass


class _ProtocolTimeout(_ProtocolError):
    pass


class NativeHidBackend:
    name = "native-hid"

    def __init__(
        self,
        path: str | None = None,
        *,
        hid_module: Any | None = None,
        control_writer: Callable[[bytes | str, bytes], None] | None = None,
        timeout: float = 0.7,
    ) -> None:
        self.path = path
        self._hid_module = hid_module
        self._control_writer = control_writer
        self.timeout = timeout

    def _hid(self) -> Any:
        if self._hid_module is not None:
            return self._hid_module
        try:
            self._hid_module = importlib.import_module("hid")
        except ImportError as exc:
            raise DependencyError(
                "The Windows HID backend requires the 'hidapi' package. "
                "Reinstall Host Slot Switch with its Windows dependencies."
            ) from exc
        return self._hid_module

    def ensure_available(self) -> None:
        self._hid()

    def version(self) -> str:
        hid = self._hid()
        version = getattr(hid, "__version__", None)
        return f"hidapi {version}" if version else "hidapi available"

    def list_devices(self) -> list[NativeDevice]:
        hid = self._hid()
        try:
            records = hid.enumerate(LOGITECH_VENDOR_ID, 0)
        except (OSError, RuntimeError) as exc:
            raise DependencyError(
                f"hidapi could not enumerate Logitech HID devices: {exc}"
            ) from exc

        devices: list[NativeDevice] = []
        failures: list[str] = []
        protocol_failures = 0
        bluetooth_candidate = False
        for record in records:
            if not self._candidate_record(record):
                continue
            path = record.get("path")
            if not path:
                continue
            control_output = self._is_bluetooth(record)
            bluetooth_candidate = bluetooth_candidate or control_output
            control_path = path if control_output else None
            handle = hid.device()
            try:
                handle.open_path(path)
                for device_index in self._candidate_indexes(record):
                    try:
                        feature_index = self._feature_index(
                            handle, device_index, CHANGE_HOST, control_path=control_path
                        )
                        if not feature_index:
                            continue
                        host_info = self._request(
                            handle,
                            device_index,
                            feature_index,
                            0x00,
                            control_path=control_path,
                        )
                        if not host_info or host_info[0] not in range(1, 4):
                            continue
                        name = self._device_name(
                            handle, device_index, control_path=control_path
                        )
                        if not name:
                            name = str(
                                record.get("product_string") or "Logitech HID++ device"
                            )
                        serial = record.get("serial_number")
                        transport = self._transport(record, device_index)
                        devices.append(
                            NativeDevice(
                                device_index,
                                name,
                                True,
                                str(serial) if serial else None,
                                transport,
                                True,
                                path,
                                control_output,
                            )
                        )
                    except (_ProtocolError, OSError, ValueError):
                        protocol_failures += 1
                        continue
            except (OSError, RuntimeError) as exc:
                failures.append(str(exc))
            finally:
                try:
                    handle.close()
                except (OSError, RuntimeError):
                    pass

        unique: dict[tuple[str, int, str], NativeDevice] = {}
        for device in devices:
            source = device.serial or self._display_path(device.path)
            key = (source, device.number, device.name.casefold())
            unique.setdefault(key, device)
        if not unique and failures:
            detail = failures[0]
            raise DeviceUnavailableError(
                "Windows could not open a Logitech HID++ collection. Close Logi "
                f"Options+ temporarily and retry. Details: {detail}"
            )
        if not unique and bluetooth_candidate and protocol_failures:
            raise DeviceUnavailableError(
                "Found a Logitech Bluetooth HID++ collection, but the device did "
                "not answer the Change Host probe. Wake the mouse, close Logi "
                "Options+ temporarily, and retry."
            )
        return list(unique.values())

    def switch(self, device: str, slot: int, *, dry_run: bool = False) -> SwitchResult:
        if slot not in range(1, 4):
            raise ValueError("slot must be between 1 and 3")
        matches = self._matching_devices(device)
        if len(matches) != 1:
            if not matches:
                raise DeviceUnavailableError(
                    f"No online Logitech HID++ device matches {device!r}. The mouse "
                    "must currently be connected to this Windows host."
                )
            names = ", ".join(match.name for match in matches)
            raise DeviceUnavailableError(
                f"Ambiguous device selector {device!r}: {names}. Use a serial or "
                "the --hid-path override."
            )
        selected = matches[0]
        command = ("native-hid", selected.name, "change-host", str(slot))
        if dry_run:
            return SwitchResult(selected.name, slot, command)

        hid = self._hid()
        handle = hid.device()
        try:
            handle.open_path(selected.path)
            control_path = selected.path if selected.control_output else None
            feature_index = self._feature_index(
                handle,
                selected.number,
                CHANGE_HOST,
                control_path=control_path,
            )
            if not feature_index:
                raise DeviceUnavailableError(
                    f"{selected.name!r} does not expose HID++ Change Host (0x1814)."
                )
            self._write(
                handle,
                selected.number,
                feature_index,
                0x10,
                bytes([slot - 1]),
                control_path=control_path,
            )
        except DeviceUnavailableError:
            raise
        except (OSError, RuntimeError, _ProtocolError) as exc:
            raise DeviceUnavailableError(
                "Windows could not send the host-switch report. The outcome may be "
                f"uncertain because a successful switch disconnects the mouse: {exc}"
            ) from exc
        finally:
            try:
                handle.close()
            except (OSError, RuntimeError):
                pass
        return SwitchResult(selected.name, slot, command)

    def _matching_devices(self, query: str) -> list[NativeDevice]:
        normalized = query.casefold().strip()
        candidates = self.list_devices()
        if self.path:
            candidates = [
                candidate
                for candidate in candidates
                if self._display_path(candidate.path) == self.path
            ]
        return [
            candidate
            for candidate in candidates
            if normalized in candidate.name.casefold()
            or (candidate.serial and normalized == candidate.serial.casefold())
            or normalized == str(candidate.number)
        ]

    def _candidate_record(self, record: Mapping[str, Any]) -> bool:
        path = record.get("path")
        if self.path and self._display_path(path) != self.path:
            return False
        usage_page = int(record.get("usage_page") or 0)
        usage = int(record.get("usage") or 0)
        if usage_page in HIDPP_USAGE_PAGES and usage in HIDPP_USAGES:
            return True
        product = str(record.get("product_string") or "").casefold()
        return "receiver" in product and int(record.get("interface_number") or -1) in {
            1,
            2,
        }

    @staticmethod
    def _candidate_indexes(record: Mapping[str, Any]) -> Sequence[int]:
        product = str(record.get("product_string") or "").casefold()
        if "receiver" in product:
            return range(1, 7)
        return (0xFF, *range(1, 7))

    @staticmethod
    def _transport(record: Mapping[str, Any], device_index: int) -> str:
        bus_value = record.get("bus_type")
        bus = (
            "bluetooth"
            if NativeHidBackend._is_bluetooth(record)
            else str(bus_value or "").replace("BUS_", "").lower()
        )
        if device_index != 0xFF:
            return f"receiver HID++ (device index {device_index})"
        return f"direct {bus} HID++" if bus else "direct HID++"

    @staticmethod
    def _is_bluetooth(record: Mapping[str, Any]) -> bool:
        bus = record.get("bus_type")
        try:
            if int(bus) == 2:
                return True
        except (TypeError, ValueError):
            pass
        return "bluetooth" in str(bus or "").casefold()

    @staticmethod
    def _display_path(path: Any) -> str:
        if isinstance(path, bytes):
            return path.decode(errors="replace")
        return str(path or "")

    def _feature_index(
        self,
        handle: Any,
        device_index: int,
        feature: int,
        *,
        control_path: bytes | str | None = None,
    ) -> int:
        reply = self._request(
            handle,
            device_index,
            0x00,
            0x00,
            bytes([(feature >> 8) & 0xFF, feature & 0xFF]),
            control_path=control_path,
        )
        return reply[0] if reply else 0

    def _device_name(
        self,
        handle: Any,
        device_index: int,
        *,
        control_path: bytes | str | None = None,
    ) -> str:
        feature_index = self._feature_index(
            handle, device_index, DEVICE_NAME, control_path=control_path
        )
        if not feature_index:
            return ""
        info = self._request(
            handle,
            device_index,
            feature_index,
            0x00,
            control_path=control_path,
        )
        if not info:
            return ""
        length = min(info[0], 128)
        name = bytearray()
        while len(name) < length:
            fragment = self._request(
                handle,
                device_index,
                feature_index,
                0x10,
                bytes([len(name)]),
                control_path=control_path,
            )
            if not fragment:
                break
            name.extend(fragment[: length - len(name)])
        return name.rstrip(b"\0").decode("utf-8", errors="replace").strip()

    def _request(
        self,
        handle: Any,
        device_index: int,
        feature_index: int,
        function: int,
        params: bytes = b"",
        *,
        control_path: bytes | str | None = None,
    ) -> bytes:
        self._drain(handle)
        request = self._packet(device_index, feature_index, function, params)
        self._write_packet(handle, request, control_path=control_path)
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _ProtocolTimeout("HID++ request timed out")
            raw = handle.read(32, max(1, int(remaining * 1000)))
            if not raw:
                continue
            reply = bytes(raw)
            if len(reply) < 4 or reply[1] != device_index:
                continue
            if (
                reply[2] == 0xFF
                and len(reply) >= 7
                and reply[3] == feature_index
                and reply[4] == (function | SOFTWARE_ID)
            ):
                raise _ProtocolError(f"HID++ feature error 0x{reply[5]:02X}")
            if reply[2] == feature_index and reply[3] == (function | SOFTWARE_ID):
                return reply[4:]

    def _write(
        self,
        handle: Any,
        device_index: int,
        feature_index: int,
        function: int,
        params: bytes,
        *,
        control_path: bytes | str | None = None,
    ) -> None:
        self._drain(handle)
        self._write_packet(
            handle,
            self._packet(device_index, feature_index, function, params),
            control_path=control_path,
        )

    @staticmethod
    def _packet(
        device_index: int, feature_index: int, function: int, params: bytes
    ) -> bytes:
        if len(params) > 16:
            raise ValueError("HID++ long report accepts at most 16 parameter bytes")
        return bytes(
            [
                HIDPP_LONG_REPORT,
                device_index,
                feature_index,
                function | SOFTWARE_ID,
            ]
        ) + params.ljust(16, b"\0")

    def _write_packet(
        self,
        handle: Any,
        packet: bytes,
        *,
        control_path: bytes | str | None = None,
    ) -> None:
        if control_path is not None:
            writer = self._control_writer or _windows_set_output_report
            writer(control_path, packet)
            return
        written = handle.write(packet)
        if written is not None and written <= 0:
            raise _ProtocolError("hidapi reported a failed HID++ write")

    @staticmethod
    def _drain(handle: Any) -> None:
        for _ in range(32):
            if not handle.read(32, 0):
                return


def _windows_set_output_report(path: bytes | str, packet: bytes) -> None:
    """Send a BLE HID output report with the acknowledged Windows control path."""
    if os.name != "nt":
        raise OSError("Windows HID control output is unavailable on this platform")

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hid = ctypes.WinDLL("hid", use_last_error=True)

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    hid.HidD_SetOutputReport.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.ULONG,
    ]
    hid.HidD_SetOutputReport.restype = wintypes.BOOLEAN

    device_path = path.decode("utf-8") if isinstance(path, bytes) else path
    generic_read_write = 0x80000000 | 0x40000000
    share_read_write = 0x00000001 | 0x00000002
    open_existing = 3
    file_flag_overlapped = 0x40000000
    native_handle = kernel32.CreateFileW(
        device_path,
        generic_read_write,
        share_read_write,
        None,
        open_existing,
        file_flag_overlapped,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if native_handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        report = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        if not hid.HidD_SetOutputReport(native_handle, report, len(packet)):
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
            raise OSError("HidD_SetOutputReport rejected the HID++ output report")
    finally:
        kernel32.CloseHandle(native_handle)
