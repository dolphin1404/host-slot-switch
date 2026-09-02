import subprocess
import unittest

from host_slot_switch.errors import DependencyError, DeviceUnavailableError
from host_slot_switch.solaar import SolaarBackend


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return self.responses.pop(0)


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class SolaarBackendTests(unittest.TestCase):
    def test_builds_safe_argument_vector(self):
        runner = FakeRunner([completed("Setting change-host")])
        backend = SolaarBackend("/usr/bin/solaar", runner=runner)
        result = backend.switch("MX Vertical; touch /tmp/nope", 2)
        self.assertEqual(
            [
                "/usr/bin/solaar",
                "config",
                "--",
                "MX Vertical; touch /tmp/nope",
                "change-host",
                "2",
            ],
            runner.commands[0][0],
        )
        self.assertEqual(2, result.slot)

    def test_dry_run_does_not_spawn_process(self):
        runner = FakeRunner([])
        backend = SolaarBackend("solaar", runner=runner)
        result = backend.switch("MX Vertical", 1, dry_run=True)
        self.assertEqual((), tuple(runner.commands))
        self.assertEqual(
            ("solaar", "config", "--", "MX Vertical", "change-host", "1"),
            result.command,
        )

    def test_option_like_device_name_is_not_parsed_by_solaar(self):
        runner = FakeRunner([completed("Setting change-host")])
        SolaarBackend("solaar", runner=runner).switch("--help", 1)
        self.assertEqual(
            ["solaar", "config", "--", "--help", "change-host", "1"],
            runner.commands[0][0],
        )

    def test_reports_offline_device(self):
        runner = FakeRunner(
            [
                completed(
                    stderr="Exception: no online device found matching 'mx vertical'",
                    returncode=1,
                )
            ]
        )
        backend = SolaarBackend("solaar", runner=runner)
        with self.assertRaisesRegex(DeviceUnavailableError, "currently controlling"):
            backend.switch("MX Vertical", 1)

    def test_parses_device_online_state(self):
        output = """Solaar version 1.1.1

Unifying Receiver
  Device path  : /dev/hidraw4
  1: MX Vertical Wireless Mouse
     Device path  : /dev/hidraw6
     Battery: unknown (device is offline).
  2: MX Keys
     Device path  : /dev/hidraw7
     Battery: 80%, discharging.
"""
        runner = FakeRunner([completed(output)])
        devices = SolaarBackend("solaar", runner=runner).list_devices()
        self.assertEqual(2, len(devices))
        self.assertFalse(devices[0].online)
        self.assertTrue(devices[1].online)

    def test_offline_state_does_not_leak_from_next_device(self):
        output = """Unifying Receiver
  1: MX Vertical Wireless Mouse
     Battery: 80%, discharging.
  2: MX Keys
     Battery: unknown (device is offline).
"""
        runner = FakeRunner([completed(output)])
        devices = SolaarBackend("solaar", runner=runner).list_devices()
        self.assertTrue(devices[0].online)
        self.assertFalse(devices[1].online)

    def test_parses_unnumbered_direct_bluetooth_device(self):
        output = """Solaar version 1.1.11

MX Vertical Wireless Mouse
     Device path  : /dev/hidraw3
     USB id       : 046d:B020
     Kind         : mouse
     Protocol     : HID++ 4.5
     Unit ID      : ABCD1234
     Supports 13 HID++ 2.0 features:
        12: CHANGE HOST {1814}
     Battery: 50%, discharging.
"""
        runner = FakeRunner([completed(output)])
        device = SolaarBackend("solaar", runner=runner).list_devices()[0]
        self.assertEqual("MX Vertical Wireless Mouse", device.name)
        self.assertTrue(device.online)
        self.assertEqual("direct/Bluetooth HID (046d:B020)", device.transport)
        self.assertTrue(device.supports_change_host)

    def test_top_level_direct_device_bounds_previous_receiver_device(self):
        output = """Unifying Receiver
  1: MX Vertical Wireless Mouse
     Kind: mouse
     Battery: 80%, discharging.
MX Anywhere
     USB id: 046d:B025
     Kind: mouse
     Battery: unknown (device is offline).
"""
        runner = FakeRunner([completed(output)])
        devices = SolaarBackend("solaar", runner=runner).list_devices()
        self.assertTrue(devices[0].online)
        self.assertFalse(devices[1].online)

    def test_nonzero_version_is_not_reported_as_available(self):
        runner = FakeRunner([completed(stderr="cannot import gtk", returncode=1)])
        with self.assertRaisesRegex(DependencyError, "could not start"):
            SolaarBackend("solaar", runner=runner).version()

    def test_nonzero_show_reports_inspection_failure(self):
        runner = FakeRunner([completed(stderr="permission denied", returncode=1)])
        with self.assertRaisesRegex(DeviceUnavailableError, "inspect devices"):
            SolaarBackend("solaar", runner=runner).list_devices()

    def test_show_uses_a_separate_longer_timeout(self):
        runner = FakeRunner([completed()])
        SolaarBackend(
            "solaar", runner=runner, timeout=3, inspect_timeout=17
        ).list_devices()
        self.assertEqual(17, runner.commands[0][1]["timeout"])

    def test_only_switch_timeout_reports_an_uncertain_outcome(self):
        def times_out(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        backend = SolaarBackend("solaar", runner=times_out)
        with self.assertRaisesRegex(
            DeviceUnavailableError, "within 20 seconds"
        ) as show:
            backend.list_devices()
        self.assertNotIn("already have been delivered", str(show.exception))
        with self.assertRaisesRegex(
            DeviceUnavailableError, "already have been delivered"
        ):
            backend.switch("MX Vertical", 1)

    def test_os_error_is_friendly(self):
        def denied(*args, **kwargs):
            raise PermissionError("not executable")

        with self.assertRaisesRegex(DependencyError, "could not run"):
            SolaarBackend("/", runner=denied).version()


if __name__ == "__main__":
    unittest.main()
