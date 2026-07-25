import json
import tempfile
import unittest
from pathlib import Path

from fiiocontrol.settings import SETTINGS_VERSION, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_defaults_to_english_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.language, "en")
            self.assertFalse(path.exists())

    def test_persists_russian_for_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            store.set_language("ru")

            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["version"], SETTINGS_VERSION)
            self.assertEqual(SettingsStore(path).language, "ru")

    def test_rejects_unknown_language_and_ignores_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            store = SettingsStore(path)
            self.assertEqual(store.language, "en")
            with self.assertRaises(ValueError):
                store.set_language("de")


if __name__ == "__main__":
    unittest.main()
