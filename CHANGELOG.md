# Changelog

All notable changes to this project will be documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-02

### Added

- Experimental native HID++ receiver and Bluetooth switching on Windows.
- Per-user Windows global-hotkey listener with login startup registration.
- A third default slot and portable angle-bracket or `Ctrl+Shift+1` syntax.
- `config path` and `config show` commands.
- PowerShell install and uninstall helpers for Windows.

## [0.1.1] - 2026-09-02

### Fixed

- Explain how to secure a group- or world-writable console entry point when
  persistent hotkey registration rejects it.
- Document the permission repair for virtual environments created with
  permissive inherited modes.

## [0.1.0] - 2026-09-02

### Added

- Solaar-backed switching by Easy-Switch slot or named profile.
- Requested defaults: laptop on slot 1 and Linux on slot 2.
- Safe GNOME global-shortcut installation and removal.
- Read-only diagnostics, dry-run mode, and JSON output.
- English and Korean documentation, MIT license, and cross-platform CI.
- Standard-library unit tests that never send hardware-changing commands.
