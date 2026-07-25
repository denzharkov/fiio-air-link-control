import unittest

from fiiocontrol.capabilities import capabilities_for_firmware


class CapabilityTests(unittest.TestCase):
    def test_enables_only_hardware_confirmed_writes(self) -> None:
        capabilities = capabilities_for_firmware("1.4.0")

        self.assertTrue(capabilities.read_device_state)
        self.assertTrue(capabilities.write_codecs)
        self.assertTrue(capabilities.write_aptx_mode)
        self.assertTrue(capabilities.write_ldac_mode)
        self.assertTrue(capabilities.manage_connections)
        self.assertTrue(capabilities.notifications)
        self.assertTrue(capabilities.pairing)
        self.assertFalse(capabilities.delete_pairing)

    def test_unknown_firmware_keeps_writes_disabled(self) -> None:
        capabilities = capabilities_for_firmware("2.0.0")
        self.assertTrue(capabilities.read_device_state)
        self.assertFalse(capabilities.write_codecs)
        self.assertTrue(capabilities.notifications)
        self.assertTrue(capabilities.pairing)


if __name__ == "__main__":
    unittest.main()
