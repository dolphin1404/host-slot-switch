# HID++ Change Host notes

Host Slot Switch does not copy or link Solaar code. The Linux backend launches
the separately installed, GPL-licensed Solaar executable through its public
CLI. This keeps the MIT-licensed application small while reusing Solaar's
mature receiver, Bluetooth, permission, and device-discovery handling.

## Wire behavior

Logitech publishes HID++ 2.0 as a self-describing protocol. Every device has a
feature table, and the root feature resolves public feature IDs to per-device
runtime indexes. Host switching is feature `0x1814`:

1. Resolve `0x1814` through `IRoot.GetFeature`.
2. `getHostInfo` returns the number of hosts and current zero-based host.
3. `setCurrentHost` accepts a zero-based host.
4. A successful set resets/disconnects the device, so there is no normal reply.

The runtime feature index and a receiver's paired-device index must never be
hard-coded. MX Vertical captures often show feature index `0x0c`, but firmware
and transport can change it. User-facing slots are 1-3; HID++ host indexes are
0-2.

## Linux command

Solaar performs discovery and conversion:

```bash
solaar config -- "MX Vertical Wireless Mouse" change-host 1
```

The device must be online on the host issuing the command. After it moves,
only the destination host can command it back.

## Sources

- [Logitech HID++ 2.0 packet format and feature list](https://github.com/Logitech/cpg-docs/blob/master/hidpp20/README.rst)
- [Logitech IRoot / dynamic feature lookup](https://github.com/Logitech/cpg-docs/blob/master/hidpp20/features/0x0000-IRoot.rst)
- [Solaar feature support table](https://github.com/pwr-Solaar/Solaar/blob/master/docs/features.md)
- [Solaar MX Vertical, Unifying WPID 407B](https://github.com/pwr-Solaar/Solaar/blob/master/docs/devices/MX%20Vertical%20Wireless%20Mouse%20407B.txt)
- [Solaar MX Vertical, Bluetooth PID B020](https://github.com/pwr-Solaar/Solaar/blob/master/docs/devices/MX%20Vertical%20Wireless%20Mouse%20B020.txt)
- [Solaar CLI used with MX Vertical `change-host`](https://github.com/pwr-Solaar/Solaar/issues/2282)
- [Solaar capabilities and online-device behavior](https://github.com/pwr-Solaar/Solaar/blob/master/docs/capabilities.md)

## Native backend requirements

A future native backend must:

- enumerate Logitech vendor HID collections, not generic mouse input;
- support direct Bluetooth and Unifying/Bolt receiver routing;
- dynamically resolve `0x1814` and the receiver device index;
- scope Linux udev access with `uaccess`, never world-writable `MODE=0666`;
- detect competing HID++ readers such as Solaar or Logi Options+;
- treat disconnect-after-write as expected success;
- test actual receiver and Bluetooth combinations on every supported OS.
