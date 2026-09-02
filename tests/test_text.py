import unittest

from host_slot_switch.text import terminal_safe


class TextTests(unittest.TestCase):
    def test_escapes_terminal_and_bidi_controls(self):
        self.assertEqual(
            "mouse\\x1b]8;;evil\\x07\\u202e",
            terminal_safe("mouse\x1b]8;;evil\x07\u202e"),
        )


if __name__ == "__main__":
    unittest.main()
