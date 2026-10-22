import unittest
from scripts.prepare_android_target import ORIGINAL, REPLACEMENT, replace_target, excluded


class PortOverlayTests(unittest.TestCase):
    def test_patches_exact_game_target(self):
        text = "start\n" + ORIGINAL + "\nend\n"
        result = replace_target(text)
        self.assertEqual(result, "start\n" + REPLACEMENT + "\nend\n")
        self.assertIn("add_library(fable_2 SHARED", result)
        self.assertIn("OUTPUT_NAME fable2", result)

    def test_refuses_changed_cmake(self):
        with self.assertRaisesRegex(ValueError, "Expected exactly one"):
            replace_target("add_executable(other_project main.cpp)")

    def test_excludes_commercial_game_data(self):
        self.assertEqual(excluded(".", [".git", "data", "default.xex", "game.iso", "src"]),
                         {".git", "data", "default.xex", "game.iso"})


if __name__ == "__main__":
    unittest.main()
