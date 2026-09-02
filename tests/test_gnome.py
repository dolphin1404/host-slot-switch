import os
import subprocess
import unittest
from unittest.mock import patch

from host_slot_switch.config import DEFAULT_CONFIG, parse_config
from host_slot_switch.errors import DesktopIntegrationError
from host_slot_switch.gnome import (
    CUSTOM_KEY,
    CUSTOM_SCHEMA,
    MEDIA_SCHEMA,
    OWN_PATH_PREFIX,
    OWN_PATHS,
    GSettings,
    build_bindings,
    ensure_gnome_desktop,
    install_hotkeys,
    parse_string_array,
    uninstall_hotkeys,
)


class MemorySettings:
    def __init__(self, paths=None):
        self.paths = list(paths or [])
        self.values = {}
        self.reset = []

    def get(self, schema, key, path=None):
        if schema == MEDIA_SCHEMA and key == CUSTOM_KEY:
            return repr(self.paths) if self.paths else "@as []"
        return repr(self.values.get((schema, path, key), ""))

    def set(self, schema, key, value, path=None):
        if schema == MEDIA_SCHEMA and key == CUSTOM_KEY:
            self.paths = parse_string_array(value)
        else:
            self.values[(schema, path, key)] = value

    def set_string(self, schema, key, value, path=None):
        self.set(schema, key, value, path)

    def reset_recursively(self, schema, path):
        self.reset.append((schema, path))


class GnomeTests(unittest.TestCase):
    def setUp(self):
        desktop = patch.dict(
            os.environ,
            {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"},
            clear=False,
        )
        desktop.start()
        self.addCleanup(desktop.stop)

    def test_gvariant_string_encoding_handles_spaces_quotes_and_unicode(self):
        commands = []

        def recording_runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        settings = GSettings("/usr/bin/gsettings", runner=recording_runner)
        settings.set_string(
            CUSTOM_SCHEMA,
            "command",
            "'/tmp/My fun/python' -m host_slot_switch # 😀",
            OWN_PATHS[0],
        )
        encoded = commands[0][-1]
        self.assertIn("😀", encoded)
        self.assertNotIn("\\ud83d", encoded)

    def test_parse_empty_typed_array(self):
        self.assertEqual([], parse_string_array("@as []"))

    def test_builds_requested_bindings(self):
        bindings = build_bindings(
            parse_config(DEFAULT_CONFIG), cli_command=["/opt/host-slot-switch"]
        )
        self.assertEqual(
            ["<Control><Shift>1", "<Control><Shift>2"],
            [b.accelerator for b in bindings],
        )
        self.assertEqual("/opt/host-slot-switch switch -- 1", bindings[0].command)

    def test_install_preserves_unrelated_shortcuts(self):
        existing = "/org/example/unrelated/"
        settings = MemorySettings([existing])
        settings.values[(CUSTOM_SCHEMA, existing, "binding")] = "<Control><Alt>9"
        bindings = install_hotkeys(
            parse_config(DEFAULT_CONFIG),
            settings,
            cli_command=["/usr/bin/host-slot-switch"],
        )
        self.assertIn(existing, settings.paths)
        self.assertTrue(all(binding.path in settings.paths for binding in bindings))

    def test_install_rejects_non_gnome_desktop_before_mutation(self):
        settings = MemorySettings(["/org/example/unrelated/"])
        with (
            patch.dict(
                os.environ,
                {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"},
                clear=False,
            ),
            self.assertRaisesRegex(DesktopIntegrationError, "GNOME desktop"),
        ):
            install_hotkeys(
                parse_config(DEFAULT_CONFIG),
                settings,
                cli_command=["host-slot-switch"],
            )
        self.assertEqual(["/org/example/unrelated/"], settings.paths)
        self.assertEqual({}, settings.values)
        self.assertEqual([], settings.reset)

    def test_gnome_desktop_detection_uses_xdg_value_authoritatively(self):
        ensure_gnome_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"})
        ensure_gnome_desktop({"DESKTOP_SESSION": "gnome-classic"})
        with self.assertRaises(DesktopIntegrationError):
            ensure_gnome_desktop(
                {"XDG_CURRENT_DESKTOP": "XFCE", "DESKTOP_SESSION": "gnome"}
            )

    def test_install_rejects_semantic_collision_before_mutation(self):
        existing = "/org/gnome/settings-daemon/custom-keybindings/unrelated/"
        settings = MemorySettings([existing])
        settings.values[(CUSTOM_SCHEMA, existing, "binding")] = "<Shift><Primary>1"
        original_paths = list(settings.paths)
        original_values = dict(settings.values)

        with self.assertRaisesRegex(DesktopIntegrationError, "already uses"):
            install_hotkeys(
                parse_config(DEFAULT_CONFIG),
                settings,
                cli_command=["host-slot-switch"],
            )

        self.assertEqual(original_paths, settings.paths)
        self.assertEqual(original_values, settings.values)
        self.assertEqual([], settings.reset)

    def test_dry_run_does_not_write(self):
        settings = MemorySettings(["/org/example/unrelated/"])
        install_hotkeys(
            parse_config(DEFAULT_CONFIG),
            settings,
            cli_command=["host-slot-switch"],
            dry_run=True,
        )
        self.assertEqual(["/org/example/unrelated/"], settings.paths)
        self.assertEqual({}, settings.values)

    def test_rejects_profile_names_with_the_same_slug(self):
        config = parse_config(
            {
                "profiles": {
                    "a b": {"slot": 1, "hotkey": "<Control>1"},
                    "a-b": {"slot": 1, "hotkey": "<Control>2"},
                }
            }
        )
        with self.assertRaisesRegex(DesktopIntegrationError, "one GNOME"):
            build_bindings(config, cli_command=["host-slot-switch"])

    def test_rejects_semantically_duplicate_accelerators(self):
        config = parse_config(
            {
                "profiles": {
                    "laptop": {"slot": 1, "hotkey": "<Control><Shift>1"},
                    "linux": {"slot": 2, "hotkey": "<Shift><Control>1"},
                }
            }
        )
        with self.assertRaisesRegex(DesktopIntegrationError, "Duplicate hotkey"):
            build_bindings(config, cli_command=["host-slot-switch"])

    def test_rejects_unparseable_or_modifierless_accelerator(self):
        config = parse_config({"profiles": {"laptop": {"slot": 1, "hotkey": "bogus"}}})
        with self.assertRaisesRegex(DesktopIntegrationError, "unsafe"):
            build_bindings(config, cli_command=["host-slot-switch"])

    def test_option_like_profile_name_is_a_positional_target(self):
        config = parse_config(
            {"profiles": {"--json": {"slot": 1, "hotkey": "<Control>1"}}}
        )
        binding = build_bindings(config, cli_command=["host-slot-switch"])[0]
        self.assertEqual(
            ["host-slot-switch", "switch", "--", "1"],
            __import__("shlex").split(binding.command),
        )

    def test_uninstall_removes_only_owned_paths(self):
        unrelated = "/org/example/unrelated/"
        owned = OWN_PATHS[0]
        settings = MemorySettings([unrelated, owned])
        removed = uninstall_hotkeys(settings)
        self.assertEqual([owned], removed)
        self.assertEqual([unrelated], settings.paths)
        self.assertEqual(1, len(settings.reset))

    def test_uninstall_preserves_unknown_similar_prefix(self):
        similar = OWN_PATH_PREFIX + "user-created/"
        settings = MemorySettings([similar, OWN_PATHS[0]])
        uninstall_hotkeys(settings)
        self.assertEqual([similar], settings.paths)

    def test_install_reconciles_stale_owned_shortcuts(self):
        config = parse_config(
            {"profiles": {"laptop": {"slot": 1, "hotkey": "<Control>1"}}}
        )
        settings = MemorySettings([OWN_PATHS[1]])
        install_hotkeys(config, settings, cli_command=["host-slot-switch"])
        self.assertEqual([OWN_PATHS[0]], settings.paths)
        self.assertEqual(1, len(settings.reset))


if __name__ == "__main__":
    unittest.main()
