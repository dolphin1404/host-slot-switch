import unittest

from host_slot_switch.native_hid import NativeHidBackend


class FakeHandle:
    def __init__(self, state):
        self.state = state
        self.replies = []

    def open_path(self, path):
        self.path = path

    def close(self):
        pass

    def write(self, packet):
        self.state["writes"].append(bytes(packet))
        self.respond(packet)
        return len(packet)

    def respond(self, packet):
        packet = bytes(packet)
        _, device, feature, function = packet[:4]
        params = packet[4:]
        if feature == 0 and params[:2] == b"\x18\x14":
            index = 0x0C if device == self.state.get("device_index", 1) else 0
            self.replies.append(bytes([0x11, device, feature, function, index, 0, 0]))
        elif (feature == 0 and params[:2] == b"\x00\x05") or (
            feature == 0x0C and function & 0xF0 == 0
        ):
            self.replies.append(bytes([0x11, device, feature, function, 3, 0, 0]))
        elif feature == 3 and function & 0xF0 == 0:
            self.replies.append(bytes([0x11, device, feature, function, 11, 0, 0]))
        elif feature == 3 and function & 0xF0 == 0x10:
            self.replies.append(
                bytes([0x11, device, feature, function]) + b"MX Vertical"
            )

    def read(self, length, timeout):
        return list(self.replies.pop(0)) if self.replies else []


class FakeHid:
    __version__ = "test"

    def __init__(self):
        self.state = {"writes": []}

    @staticmethod
    def enumerate(vendor, product):
        return [
            {
                "path": b"receiver-hidpp",
                "vendor_id": vendor,
                "product_id": 0xC52B,
                "product_string": "USB Receiver",
                "usage_page": 0xFF00,
                "usage": 0x0001,
                "interface_number": 2,
            }
        ]

    def device(self):
        self.current_handle = FakeHandle(self.state)
        return self.current_handle


class BluetoothFakeHid(FakeHid):
    def __init__(self):
        super().__init__()
        self.state["device_index"] = 0xFF
        self.state["control_writes"] = []

    @staticmethod
    def enumerate(vendor, product):
        return [
            {
                "path": b"mx-vertical-bluetooth-hidpp",
                "vendor_id": vendor,
                "product_id": 0xB020,
                "product_string": "MX_Vertical",
                "usage_page": 0xFF43,
                "usage": 0x0202,
                "interface_number": -1,
                "bus_type": 2,
            }
        ]

    def write_control(self, path, packet):
        self.state["control_writes"].append((path, bytes(packet)))
        self.current_handle.respond(packet)


class NativeHidTests(unittest.TestCase):
    def test_discovers_feature_and_switches_zero_based_host(self):
        hid = FakeHid()
        backend = NativeHidBackend(hid_module=hid, timeout=0.001)
        devices = backend.list_devices()
        self.assertEqual(["MX Vertical"], [device.name for device in devices])
        self.assertEqual(1, devices[0].number)
        self.assertTrue(devices[0].supports_change_host)

        result = backend.switch("MX Vertical", 3)
        self.assertEqual(3, result.slot)
        change_host = [
            packet
            for packet in hid.state["writes"]
            if packet[2] == 0x0C and packet[3] & 0xF0 == 0x10
        ][-1]
        self.assertEqual(2, change_host[4])

    def test_dry_run_does_not_send_change_host(self):
        hid = FakeHid()
        backend = NativeHidBackend(hid_module=hid, timeout=0.001)
        backend.switch("MX Vertical", 2, dry_run=True)
        self.assertFalse(
            any(
                packet[2] == 0x0C and packet[3] & 0xF0 == 0x10
                for packet in hid.state["writes"]
            )
        )

    def test_bluetooth_uses_windows_control_output_reports(self):
        hid = BluetoothFakeHid()
        backend = NativeHidBackend(
            hid_module=hid,
            control_writer=hid.write_control,
            timeout=0.001,
        )

        devices = backend.list_devices()
        self.assertEqual(["MX Vertical"], [device.name for device in devices])
        self.assertEqual(0xFF, devices[0].number)
        self.assertEqual("direct bluetooth HID++", devices[0].transport)
        self.assertTrue(devices[0].control_output)

        backend.switch("MX Vertical", 1)
        self.assertEqual([], hid.state["writes"])
        change_host = [
            packet
            for _, packet in hid.state["control_writes"]
            if packet[2] == 0x0C and packet[3] & 0xF0 == 0x10
        ][-1]
        self.assertEqual(0, change_host[4])


if __name__ == "__main__":
    unittest.main()
