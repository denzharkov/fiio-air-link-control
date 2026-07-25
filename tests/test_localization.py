import unittest

from fiiocontrol.localization import localize_document, translate_text


class LocalizationTests(unittest.TestCase):
    def test_translates_document_recursively_to_english(self) -> None:
        document = {
            "title": "Устройства",
            "children": ["Добавить новое устройство", {"value": "Нет данных"}],
        }
        self.assertEqual(
            localize_document(document, "en"),
            {
                "title": "Devices",
                "children": ["Add new device", {"value": "No data"}],
            },
        )
        self.assertIs(localize_document(document, "ru"), document)

    def test_translates_dynamic_runtime_statuses(self) -> None:
        self.assertEqual(translate_text("Прошивка 1.4.0"), "Firmware 1.4.0")
        self.assertEqual(
            translate_text("Подключено; гарнитур: 1; LE: 0"),
            "Connected; headsets: 1; LE: 0",
        )
        self.assertEqual(
            translate_text("Ошибка: Некорректный Bluetooth-адрес"),
            "Error: Invalid Bluetooth address",
        )


if __name__ == "__main__":
    unittest.main()
