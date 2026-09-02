from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import default_config_path, load_config, write_default_config
from .doctor import checks_as_dicts, run_checks
from .errors import MxEasySwitchError
from .gnome import (
    GSettings,
    discover_cli_command,
    install_hotkeys,
    uninstall_hotkeys,
)
from .locking import switch_lock
from .solaar import SolaarBackend
from .text import terminal_safe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="host-slot-switch",
        description="Switch Logitech Easy-Switch slots without turning the mouse over.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--config", type=Path, help="config path (default: XDG config directory)"
    )
    parser.add_argument("--device", help="override the Solaar device name/sub-string")
    parser.add_argument("--solaar", help="path to the Solaar executable")
    subparsers = parser.add_subparsers(dest="command", required=True)

    switch = subparsers.add_parser(
        "switch", help="switch to a profile name or slot 1-3"
    )
    switch.add_argument("target", help="profile name (for example laptop) or slot 1-3")
    switch.add_argument(
        "--dry-run", action="store_true", help="print without changing the mouse"
    )
    switch.add_argument("--json", action="store_true", help="machine-readable output")

    doctor = subparsers.add_parser(
        "doctor", help="check Solaar, receiver and mouse state"
    )
    doctor.add_argument("--json", action="store_true", help="machine-readable output")

    config = subparsers.add_parser("config", help="create the default configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    init = config_sub.add_parser("init", help="write the default slot/profile mapping")
    init.add_argument("--force", action="store_true", help="replace an existing config")

    hotkeys = subparsers.add_parser("hotkeys", help="manage GNOME global shortcuts")
    hotkeys_sub = hotkeys.add_subparsers(dest="hotkeys_command", required=True)
    hotkeys_install = hotkeys_sub.add_parser(
        "install", help="install configured GNOME shortcuts"
    )
    hotkeys_install.add_argument("--dry-run", action="store_true")
    hotkeys_remove = hotkeys_sub.add_parser(
        "uninstall", help="remove only this app's shortcuts"
    )
    hotkeys_remove.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "config":
            path = write_default_config(args.config, force=args.force)
            print(f"Wrote {terminal_safe(path)}")
            return 0

        if args.command == "hotkeys" and args.hotkeys_command == "uninstall":
            settings = GSettings()
            if args.dry_run:
                paths = uninstall_hotkeys(settings, dry_run=True)
            else:
                with switch_lock("gnome-hotkeys"):
                    paths = uninstall_hotkeys(settings)
            verb = "Would remove" if args.dry_run else "Removed"
            print(f"{verb} {len(paths)} Host Slot Switch shortcut(s).")
            return 0

        config = load_config(args.config)
        device = args.device or config.device
        backend = SolaarBackend(args.solaar)

        if args.command == "switch":
            slot = config.resolve_target(args.target)
            if args.dry_run:
                result = backend.switch(device, slot, dry_run=True)
            else:
                with switch_lock("device-switch"):
                    result = backend.switch(device, slot)
            if args.json:
                print(
                    json.dumps(
                        {
                            "device": result.device,
                            "slot": result.slot,
                            "dry_run": args.dry_run,
                            "command": list(result.command),
                        },
                        ensure_ascii=True,
                    )
                )
            elif args.dry_run:
                print(terminal_safe(shlex.join(result.command)))
            else:
                print(
                    f"Switch command sent to {terminal_safe(result.device)!r}: "
                    f"Easy-Switch slot {slot}."
                )
            return 0

        if args.command == "doctor":
            checks = run_checks(config, backend, device=device)
            if args.json:
                print(json.dumps(checks_as_dicts(checks), indent=2, ensure_ascii=True))
            else:
                for check in checks:
                    mark = "OK" if check.ok else "!!"
                    print(
                        f"[{mark}] {terminal_safe(check.name)}: "
                        f"{terminal_safe(check.detail)}"
                    )
            return 0 if all(check.ok for check in checks) else 1

        if args.command == "hotkeys":
            settings = GSettings()
            if args.hotkeys_command == "install":
                shortcut_command = [
                    *discover_cli_command(),
                ]
                shortcut_config = args.config or default_config_path()
                if (
                    args.config
                    or os.environ.get("HOST_SLOT_SWITCH_CONFIG")
                    or shortcut_config.exists()
                ):
                    shortcut_command.extend(
                        [f"--config={shortcut_config.expanduser().resolve()}"]
                    )
                if args.device:
                    shortcut_command.append(f"--device={args.device}")
                if args.solaar:
                    shortcut_command.append(f"--solaar={args.solaar}")
                if args.dry_run:
                    bindings = install_hotkeys(
                        config,
                        settings,
                        cli_command=shortcut_command,
                        dry_run=True,
                    )
                else:
                    with switch_lock("gnome-hotkeys"):
                        bindings = install_hotkeys(
                            config,
                            settings,
                            cli_command=shortcut_command,
                        )
                verb = "Would install" if args.dry_run else "Installed"
                for binding in bindings:
                    message = (
                        f"{verb} {binding.accelerator} -> "
                        f"{binding.profile} (slot {binding.slot})"
                    )
                    if args.dry_run:
                        message += f": {binding.command}"
                    print(terminal_safe(message))
            return 0

        raise AssertionError(f"Unhandled command: {args.command}")
    except MxEasySwitchError as exc:
        print(f"host-slot-switch: {terminal_safe(exc)}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
