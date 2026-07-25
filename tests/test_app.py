import unittest

from fiiocontrol.app import BduiBackend
from fiiocontrol.device import CODECS


class AppValidationTests(unittest.TestCase):
    def test_requires_complete_boolean_codec_payload(self) -> None:
        valid = {name: name == "ldac" for name in CODECS}
        self.assertEqual(BduiBackend._validate_codecs(valid), valid)

        for invalid in (
            None,
            {},
            {**valid, "unknown": False},
            {name: value for name, value in valid.items() if name != "ldac"},
            {**valid, "ldac": 1},
        ):
            with self.assertRaises(ValueError):
                BduiBackend._validate_codecs(invalid)

    def test_validates_bluetooth_address_payload(self) -> None:
        self.assertEqual(
            BduiBackend._validate_address({"address": [1, 2, 3, 4, 5, 6]}),
            (1, 2, 3, 4, 5, 6),
        )
        for invalid in (
            None,
            {},
            {"address": [1, 2]},
            {"address": [1, 2, 3, 4, 5, 256]},
            {"address": [1, 2, 3, 4, 5, True]},
        ):
            with self.assertRaises(ValueError):
                BduiBackend._validate_address(invalid)


if __name__ == "__main__":
    unittest.main()
