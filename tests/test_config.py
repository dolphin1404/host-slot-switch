import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from host_slot_switch.config import (
    DEFAULT_CONFIG,
    MAX_CONFIG_BYTES,
    ConfigurationError,
    load_config,
    parse_config,
    write_default_config,
)


class ConfigTests(unittest.TestCase):
    def test_example_config_stays_in_sync_with_defaults(self):
        example = Path(__file__).resolve().parent.parent / "config.example.json"
        self.assertEqual(
            DEFAULT_CONFIG, json.loads(example.read_text(encoding="utf-8"))
        )

    def test_defaults_match_requested_slots(self):
        config = parse_config(DEFAULT_CONFIG)
        self.assertEqual(1, config.resolve_target("laptop"))
        self.assertEqual(2, config.resolve_target("LINUX"))
        self.assertEqual(3, config.resolve_target("3"))

    def test_unknown_profile_has_actionable_error(self):
        config = parse_config(DEFAULT_CONFIG)
        with self.assertRaisesRegex(ConfigurationError, "laptop, linux"):
            config.resolve_target("desktop")

    def test_rejects_invalid_slot(self):
        raw = dict(DEFAULT_CONFIG)
        raw["profiles"] = {"bad": {"slot": 0}}
        with self.assertRaisesRegex(ConfigurationError, "slot from 1 to 3"):
            parse_config(raw)

    def test_rejects_boolean_slot(self):
        with self.assertRaisesRegex(ConfigurationError, "slot from 1 to 3"):
            parse_config({"profiles": {"bad": {"slot": True}}})

    def test_rejects_unsupported_backend(self):
        with self.assertRaisesRegex(ConfigurationError, "Only the 'solaar'"):
            parse_config({"backend": "raw-hid", "profiles": {"laptop": {"slot": 1}}})

    def test_rejects_numeric_profile_names(self):
        with self.assertRaisesRegex(ConfigurationError, "reserved"):
            parse_config({"profiles": {"1": {"slot": 2}}})

    def test_rejects_unknown_top_level_key(self):
        with self.assertRaisesRegex(ConfigurationError, "profiels"):
            parse_config({"profiels": {"laptop": {"slot": 1}}})

    def test_rejects_unknown_profile_key(self):
        with self.assertRaisesRegex(ConfigurationError, "hoteky"):
            parse_config({"profiles": {"laptop": {"slot": 1, "hoteky": "<Control>1"}}})

    def test_trims_hotkey_whitespace(self):
        config = parse_config(
            {"profiles": {"laptop": {"slot": 1, "hotkey": "  <Control>1  "}}}
        )
        self.assertEqual("<Control>1", config.profiles["laptop"].hotkey)

    def test_write_and_load_default_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            written = write_default_config(path)
            self.assertEqual(path, written)
            self.assertEqual(1, load_config(path).profiles["laptop"].slot)
            with self.assertRaises(ConfigurationError):
                write_default_config(path)

    def test_loads_user_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "device": "MX Vertical Wireless Mouse",
                        "profiles": {"notebook": {"slot": 3, "hotkey": "<Control>3"}},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual("MX Vertical Wireless Mouse", config.device)
            self.assertEqual(3, config.resolve_target("notebook"))

    def test_explicit_missing_config_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "typo.json"
            with self.assertRaisesRegex(ConfigurationError, "does not exist"):
                load_config(path)

    def test_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text('{"device":"one","device":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "Duplicate JSON key"):
                load_config(path)

    def test_rejects_oversized_config_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_bytes(b" " * (MAX_CONFIG_BYTES + 1))
            with self.assertRaisesRegex(ConfigurationError, "larger than"):
                load_config(path)

    def test_rejects_non_regular_config(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            self.assertRaisesRegex(ConfigurationError, "regular file"),
        ):
            load_config(Path(temp))

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics")
    def test_default_config_is_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private" / "config.json"
            write_default_config(path)
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE(path.parent.stat().st_mode))

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_force_refuses_config_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.json"
            target.write_text("keep", encoding="utf-8")
            link = root / "config.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ConfigurationError, "symlink"):
                write_default_config(link, force=True)
            self.assertEqual("keep", target.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_load_refuses_config_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.json"
            target.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
            link = root / "config.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ConfigurationError, "symbolic link"):
                load_config(link)

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics")
    def test_load_refuses_group_or_world_writable_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
            path.chmod(0o666)
            with self.assertRaisesRegex(ConfigurationError, "group/world writable"):
                load_config(path)

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics")
    def test_force_replacement_remains_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text("{}", encoding="utf-8")
            path.chmod(0o644)
            write_default_config(path, force=True)
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics")
    def test_rejects_writable_config_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "config-parent"
            parent.mkdir()
            parent.chmod(0o777)
            with self.assertRaisesRegex(ConfigurationError, "parent.*writable"):
                write_default_config(parent / "config.json")

    def test_parent_file_error_is_friendly(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "not-a-directory"
            parent.write_text("content", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                write_default_config(parent / "config.json")


if __name__ == "__main__":
    unittest.main()
