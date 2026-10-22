import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeTouchTests(unittest.TestCase):
    def test_native_java_interface_matches(self):
        j = (ROOT / 'port/android/java/com/nanaveone/fable2/Fable2TouchControls.java').read_text()
        c = (ROOT / 'port/android/native/fable2_touch.cpp').read_text()
        for name in ('nativeAttach', 'nativeButton', 'nativeAxis'):
            self.assertIn(f'native {"boolean" if name == "nativeAttach" else "void"} {name}', j)
            self.assertIn('Java_com_nanaveone_fable2_Fable2TouchControls_' + name, c)
        self.assertIn('SDL_AttachVirtualJoystick', c)
        self.assertIn('SDL_SetJoystickVirtualButton', c)
        self.assertIn('SDL_SetJoystickVirtualAxis', c)
        self.assertIn('SDL_JOYSTICK_TYPE_GAMEPAD', c)

    def test_game_activity_provides_writable_paths_and_touch(self):
        s = (ROOT / 'port/android/java/com/nanaveone/fable2/Fable2Activity.java').read_text()
        self.assertIn('FABLE2_GAME_ROOT', s)
        self.assertIn('FABLE2_USER_ROOT', s)
        self.assertIn('new Fable2TouchControls(this)', s)
        self.assertIn('"rexruntime", "fable2"', s)

    def test_no_game_binaries_in_artifact(self):
        for path in ROOT.rglob('*'):
            if path.is_file():
                self.assertNotIn(path.suffix.lower(), {'.xex', '.iso', '.god'})


if __name__ == '__main__':
    unittest.main()
