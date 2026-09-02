from __future__ import annotations

import platform
from typing import Protocol

from .config import Config
from .errors import ConfigurationError
from .native_hid import NativeHidBackend
from .solaar import SolaarBackend, SolaarDevice, SwitchResult


class Backend(Protocol):
    name: str

    def version(self) -> str | None: ...

    def list_devices(self) -> list[SolaarDevice]: ...

    def switch(
        self, device: str, slot: int, *, dry_run: bool = False
    ) -> SwitchResult: ...


def create_backend(
    config: Config,
    *,
    solaar: str | None = None,
    hid_path: str | None = None,
    system: str | None = None,
) -> Backend:
    selected = config.backend
    system = system or platform.system()
    if selected == "auto":
        selected = "native-hid" if system == "Windows" else "solaar"
    if selected == "solaar":
        return SolaarBackend(solaar)
    if selected == "native-hid":
        if system != "Windows":
            raise ConfigurationError(
                "The native-hid backend is currently supported only on Windows."
            )
        return NativeHidBackend(path=hid_path)
    raise AssertionError(f"Unhandled backend: {selected}")
