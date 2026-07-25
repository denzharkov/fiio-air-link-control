import unittest

from fiiocontrol.build_info import BuildInfo


class BuildInfoTests(unittest.TestCase):
    def test_formats_commit_and_dirty_state(self) -> None:
        self.assertEqual(
            BuildInfo("0.2.0", "0123456789abcdef", False).display_commit,
            "01234567",
        )
        self.assertEqual(
            BuildInfo("0.2.0", "0123456789abcdef", True).display_commit,
            "01234567-dirty",
        )
        self.assertEqual(BuildInfo("0.2.0", None, False).display_commit, "unknown")


if __name__ == "__main__":
    unittest.main()
