# Contributing

Bug reports should include the output of:

```bash
host-slot-switch doctor --json
solaar show
```

Remove serial numbers before posting logs publicly. Do not attach raw dumps that
contain unrelated keyboard input.

For code changes:

1. Keep the core dependency-free unless a dependency materially reduces HID
   safety or platform-specific complexity.
2. Never hard-code a HID++ feature index, receiver pairing index, or device
   serial number.
3. Add unit tests that use a fake transport. Hardware-changing tests must be
   opt-in and clearly labeled.
4. Run `make test` before opening a pull request.

The project uses the MIT license. Contributions are submitted under the same
license.
