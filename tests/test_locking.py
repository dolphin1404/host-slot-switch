import tempfile
import unittest
from pathlib import Path

from host_slot_switch.errors import DeviceUnavailableError
from host_slot_switch.locking import switch_lock


class LockingTests(unittest.TestCase):
    def test_rejects_concurrent_switch_for_same_device(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "locks"
            with (
                switch_lock("MX Vertical", directory=directory),
                self.assertRaisesRegex(DeviceUnavailableError, "already in progress"),
                switch_lock("mx vertical", directory=directory),
            ):
                self.fail("the second lock must not be acquired")

    def test_different_devices_have_different_locks(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "locks"
            with (
                switch_lock("Mouse A", directory=directory),
                switch_lock("Mouse B", directory=directory),
            ):
                pass


if __name__ == "__main__":
    unittest.main()
