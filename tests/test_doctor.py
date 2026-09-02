import os
import unittest
from unittest.mock import patch

from host_slot_switch.config import DEFAULT_CONFIG, parse_config
from host_slot_switch.doctor import run_checks
from host_slot_switch.solaar import SolaarDevice


class StubBackend:
    name = "solaar"

    def __init__(self, devices):
        self.devices = devices

    def version(self):
        return "solaar 1.2.3"

    def list_devices(self):
        return self.devices


class DoctorTests(unittest.TestCase):
    def test_desktop_check_rejects_non_gnome_false_success(self):
        backend = StubBackend([])
        with (
            patch.dict(
                os.environ,
                {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"},
                clear=False,
            ),
            patch("host_slot_switch.doctor.platform.system", return_value="Linux"),
        ):
            checks = run_checks(parse_config(DEFAULT_CONFIG), backend)
        desktop = next(check for check in checks if check.name == "desktop")
        self.assertFalse(desktop.ok)
        self.assertIn("bind commands manually", desktop.detail)

    def test_desktop_check_accepts_gnome(self):
        backend = StubBackend([])
        with (
            patch.dict(
                os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, clear=False
            ),
            patch("host_slot_switch.doctor.platform.system", return_value="Linux"),
        ):
            checks = run_checks(parse_config(DEFAULT_CONFIG), backend)
        desktop = next(check for check in checks if check.name == "desktop")
        self.assertTrue(desktop.ok)

    def test_desktop_check_accepts_windows_hotkey_service(self):
        backend = StubBackend([])
        with patch("host_slot_switch.doctor.platform.system", return_value="Windows"):
            checks = run_checks(parse_config(DEFAULT_CONFIG), backend)
        desktop = next(check for check in checks if check.name == "desktop")
        self.assertTrue(desktop.ok)
        self.assertIn("RegisterHotKey", desktop.detail)

    def test_reports_transport_and_change_host_capability(self):
        backend = StubBackend(
            [
                SolaarDevice(
                    1,
                    "MX Vertical Wireless Mouse",
                    True,
                    "ABC123",
                    "receiver (WPID 407B)",
                    True,
                )
            ]
        )
        checks = run_checks(parse_config(DEFAULT_CONFIG), backend)
        by_name = {check.name: check for check in checks}
        self.assertTrue(by_name["device"].ok)
        self.assertTrue(by_name["transport"].ok)
        self.assertTrue(by_name["change-host"].ok)

    def test_rejects_ambiguous_device_selector(self):
        backend = StubBackend(
            [
                SolaarDevice(1, "MX Vertical A", True),
                SolaarDevice(2, "MX Vertical B", True),
            ]
        )
        checks = run_checks(parse_config(DEFAULT_CONFIG), backend)
        device = next(check for check in checks if check.name == "device")
        self.assertFalse(device.ok)
        self.assertIn("Ambiguous", device.detail)

    def test_device_override_is_used(self):
        backend = StubBackend([SolaarDevice(1, "Other Mouse", True)])
        checks = run_checks(parse_config(DEFAULT_CONFIG), backend, device="Other Mouse")
        device = next(check for check in checks if check.name == "device")
        self.assertTrue(device.ok)


if __name__ == "__main__":
    unittest.main()
