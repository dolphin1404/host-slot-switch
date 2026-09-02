import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from host_slot_switch import __version__
from host_slot_switch.cli import main
from host_slot_switch.config import DEFAULT_CONFIG


class CliTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        declared = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in pyproject.read_text(encoding="utf-8").splitlines()
            if line.startswith("version = ")
        )
        self.assertEqual(declared, __version__)

    def test_switch_dry_run(self):
        stdout = io.StringIO()
        with (
            patch(
                "host_slot_switch.solaar.shutil.which", return_value="/usr/bin/solaar"
            ),
            redirect_stdout(stdout),
        ):
            code = main(["switch", "laptop", "--dry-run"])
        self.assertEqual(0, code)
        self.assertIn("change-host 1", stdout.getvalue())

    def test_invalid_slot_is_friendly(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["switch", "9", "--dry-run"])
        self.assertEqual(2, code)
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_hotkey_command_keeps_custom_config_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
            stdout = io.StringIO()
            with (
                patch(
                    "host_slot_switch.gnome.shutil.which",
                    side_effect=lambda name: f"/usr/bin/{name}",
                ),
                patch(
                    "host_slot_switch.cli.discover_cli_command",
                    return_value=["/opt/host-slot-switch"],
                ),
                redirect_stdout(stdout),
            ):
                code = main(
                    [
                        "--config",
                        str(path),
                        "--device=--help",
                        "hotkeys",
                        "install",
                        "--dry-run",
                    ]
                )
        self.assertEqual(0, code)
        self.assertIn("Would install <Control><Shift>1", stdout.getvalue())
        self.assertIn(str(path.resolve()), stdout.getvalue())
        self.assertIn("--device=--help", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
