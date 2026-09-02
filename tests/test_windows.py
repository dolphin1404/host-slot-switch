import unittest

from host_slot_switch.config import DEFAULT_CONFIG, parse_config
from host_slot_switch.errors import DesktopIntegrationError
from host_slot_switch.windows import (
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    build_windows_bindings,
    parse_windows_hotkey,
)


class WindowsTests(unittest.TestCase):
    def test_accepts_portable_and_windows_hotkey_syntax(self):
        angle = parse_windows_hotkey("<Control><Shift>1")
        plus = parse_windows_hotkey("Ctrl+Shift+1")
        self.assertEqual(angle, plus)
        self.assertEqual(MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, angle[0])
        self.assertEqual(ord("1"), angle[1])

    def test_default_config_covers_all_three_slots(self):
        bindings = build_windows_bindings(parse_config(DEFAULT_CONFIG))
        self.assertEqual([1, 2, 3], [binding.slot for binding in bindings])

    def test_rejects_unsafe_modifierless_hotkey(self):
        with self.assertRaises(DesktopIntegrationError):
            parse_windows_hotkey("Shift+1")


if __name__ == "__main__":
    unittest.main()
