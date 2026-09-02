# Host Slot Switch

[한국어 설명](https://github.com/dolphin1404/host-slot-switch/blob/main/README.ko.md)

Switch host slots with a keyboard shortcut instead of reaching for a device's
physical selector. This independent project is tested with the Logitech®
MX Vertical™ Advanced Ergonomic Mouse and its Easy-Switch™ host slots.

The default mapping matches this project's original setup:

| Shortcut | Profile | Easy-Switch slot |
| --- | --- | ---: |
| `Ctrl+Shift+1` | laptop | 1 |
| `Ctrl+Shift+2` | Linux desktop | 2 |

Host Slot Switch is a small, dependency-free Python CLI. On Linux it delegates
device discovery and HID++ transport to [Solaar](https://pwr-solaar.github.io/Solaar/),
then uses GNOME's own global-shortcut settings. It does not need a network,
run as root, or keep a background daemon alive.

## Important physical constraint

The command can only be sent by the computer to which the mouse is **currently
connected**. Install the tool on both computers for round-trip switching:

```text
Linux (mouse is on slot 2)  -- Ctrl+Shift+1 -->  laptop (slot 1)
laptop (mouse is on slot 1) -- Ctrl+Shift+2 -->  Linux (slot 2)
```

Platform support in `0.1.0` is deliberately narrow:

| Host | Switching CLI | Global-shortcut installer | Status |
| --- | --- | --- | --- |
| Linux + Solaar | Yes | GNOME X11/Wayland | Tested |
| macOS + Solaar | Experimental | No | Solaar itself has limited macOS support |
| Windows | No | No | Native HID++ backend is on the roadmap |

If the laptop runs Windows, this version cannot perform the return trip from
slot 1 to Linux without the physical button. Do not use hard-coded raw HID
frames as a workaround: both the receiver device index and feature index are
discovered at runtime.

## Requirements

- Python 3.10 or newer
- Solaar
- A compatible device exposing HID++ `CHANGE_HOST` (`0x1814`)
- The mouse already paired to the desired Easy-Switch slots

The Logitech MX Vertical mouse is known to expose this feature over both
Unifying and Bluetooth. This repository was developed against WPID `407B` and
Unifying receiver `046d:c52b` on Ubuntu 22.04/GNOME X11.

## Install

From a downloaded or cloned source checkout, change into the repository root.
Then, on Ubuntu/Debian:

```bash
sudo apt install solaar python3-venv
python3 -m venv ~/.local/share/host-slot-switch/venv
~/.local/share/host-slot-switch/venv/bin/pip install .
~/.local/share/host-slot-switch/venv/bin/host-slot-switch config init
~/.local/share/host-slot-switch/venv/bin/host-slot-switch doctor
```

Only the first `apt` command shown above uses `sudo`. Run every subsequent
`host-slot-switch`, `pip`, and Solaar command as the logged-in desktop user. Never
add a world-writable (`MODE=0666`) hidraw rule; use the udev rule supplied by
the Solaar package.

An `offline` result does not identify one specific cause: the mouse may be
asleep, powered off, out of range, or connected to another host. Wake and move
the mouse first. If it remains offline, select this computer's slot once with
the physical button before the first software-switch test.

Run `doctor` before installing hotkeys and proceed only when it identifies one
intended device and verifies `change-host`. If it reports an ambiguous device
selector, find the intended mouse's serial with `solaar show`, then either put
that serial in the config's `device` field or verify and persist the override:

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL doctor
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL hotkeys install --dry-run
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL hotkeys install
```

Treat device serials as private when sharing logs.

Preview and install GNOME global shortcuts:

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys install --dry-run
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys install
```

The installer preserves existing custom shortcuts and owns only these three
exact dconf paths:

```text
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-1/
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-2/
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-3/
```

Similar names that merely start with `host-slot-switch-` are not removed. Remove
the app-owned shortcuts with:

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys uninstall
```

For KDE, Xfce, or another desktop, bind these commands with the desktop's
shortcut settings:

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch switch laptop
~/.local/share/host-slot-switch/venv/bin/host-slot-switch switch linux
```

## CLI

```console
$ host-slot-switch switch laptop --dry-run
/usr/bin/solaar config -- 'MX Vertical' change-host 1

$ host-slot-switch doctor
[OK] platform: Linux-...
[OK] desktop: ubuntu:GNOME
[OK] solaar: solaar 1.1.19
[OK] device: MX Vertical Wireless Mouse (online)
[OK] transport: receiver (WPID 407B)
[OK] change-host: HID++ feature 0x1814
```

Available commands:

- `switch <profile|1|2|3>` sends a host-change command.
- `doctor` checks the platform, Solaar, receiver, and online state.
- `config init` writes the default profile mapping.
- `hotkeys install|uninstall` manages GNOME shortcuts without touching others.

All subprocesses use argument arrays rather than a shell. `switch` reports that
the command was sent—not that a reply arrived—because a successful host change
immediately disconnects the device by design. A timeout has an uncertain
outcome: do not press the shortcut again or configure an automatic retry. First
check whether the mouse reached the destination host; if it is unreachable,
recover with the physical Easy-Switch button.

## Configuration

The default file is `~/.config/host-slot-switch/config.json`:

```json
{
  "device": "MX Vertical",
  "backend": "solaar",
  "profiles": {
    "laptop": {"slot": 1, "hotkey": "<Control><Shift>1"},
    "linux": {"slot": 2, "hotkey": "<Control><Shift>2"}
  }
}
```

Use `--config PATH` or the `HOST_SLOT_SWITCH_CONFIG` environment variable for a
different file. Profile names are case-insensitive; slots are always 1-based.
Unknown or duplicate JSON keys are rejected instead of silently falling back
to a potentially wrong slot.

Configuration files are limited to 1 MiB and must be regular, current-user
owned, and not group/world writable. Symlinks are intentionally rejected. Files
created by `config init` use mode `0600` inside a `0700` app directory. If a
manually created config is rejected, run `chmod 600 CONFIG_PATH`.

GNOME allows one configured shortcut per Easy-Switch slot. The installer
accepts conservative GDK accelerators such as `<Control><Shift>1`,
`<Alt>F8`, or `<Super>Home`; run `hotkeys install --dry-run` before changing
the desktop settings. A malformed accelerator or two semantic spellings of the
same key are rejected.
Existing GNOME custom shortcuts are checked for semantic accelerator collisions
before any desktop setting is changed.

## Development

```bash
make test
make dry-run
```

The test suite uses only the Python standard library and never sends an HID++
command. See [the protocol notes](https://github.com/dolphin1404/host-slot-switch/blob/main/docs/PROTOCOL.md)
for the hardware behavior and implementation references.

## Status and roadmap

- [x] Safe Solaar backend
- [x] Named profiles and slots 1-3
- [x] GNOME X11/Wayland global shortcuts
- [x] Transport/`0x1814` diagnostics, dry-run, JSON output, unit tests, CI
- [ ] Native receiver/Bluetooth HID++ backend for Windows
- [ ] macOS shortcut installer
- [ ] KDE shortcut installer
- [ ] `.deb`, Windows portable, and signed release artifacts

## Security reporting

Use this GitHub repository's **Security → Report a vulnerability** form for a
private report; see the [security policy](https://github.com/dolphin1404/host-slot-switch/blob/main/SECURITY.md).
Do not include exploit details, device serials, or logs in a public issue. If
the private-reporting button is not available, open a public issue with no
sensitive details and ask the maintainer for a private contact channel.

## License, independence, and trademarks

MIT. This project contains no Logitech software, firmware, logos, or product
imagery, and does not copy or link Solaar code. Solaar is a separately installed
GPL-2.0 program invoked through its command-line interface. See
[NOTICE.md](https://github.com/dolphin1404/host-slot-switch/blob/main/NOTICE.md).

Host Slot Switch is an independent project and is not affiliated with,
sponsored by, or endorsed by Logitech. Logitech, Logi, and their logos are
trademarks or registered trademarks of Logitech Europe S.A. and/or its
affiliates in the United States and/or other countries. MX Vertical and
Easy-Switch are trademarks of their respective owner. All product names are
used solely to identify compatibility.
