import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANDROID = "{http://schemas.android.com/apk/res/android}"


class AndroidLauncherTests(unittest.TestCase):
    def test_launcher_and_game_activities_are_distinct(self):
        root = ET.parse(ROOT / "port/android/AndroidManifest.xml").getroot()
        activities = root.findall("application/activity")
        names = {x.attrib.get(ANDROID + "name") for x in activities}
        self.assertIn(".Fable2LauncherActivity", names)
        self.assertIn(".Fable2Activity", names)
        exported = {x.attrib.get(ANDROID + "name"): x.attrib.get(ANDROID + "exported") for x in activities}
        self.assertEqual(exported[".Fable2Activity"], "false")
        self.assertEqual(exported[".Fable2LauncherActivity"], "true")

    def test_importer_uses_scoped_storage(self):
        contents = (ROOT / "port/android/java/com/nanaveone/fable2/Fable2LauncherActivity.java").read_text()
        self.assertIn("Intent.ACTION_OPEN_DOCUMENT_TREE", contents)
        self.assertIn("getContentResolver().openInputStream", contents)
        self.assertIn('"default.xex"', contents)
        self.assertIn('"data"', contents)
        self.assertIn("getCanonicalPath", contents)
        self.assertNotIn("MANAGE_EXTERNAL_STORAGE", contents)

    def test_apk_script_requires_real_game_libs(self):
        shell = (ROOT / "scripts/package_android_apk.sh").read_text()
        for library in ("libfable2.so", "librexruntime.so", "librexgpu-plume.so"):
            self.assertIn(library, shell)
        self.assertIn("Missing $libdir/$lib", shell)
        self.assertIn("apksigner", shell)


if __name__ == "__main__":
    unittest.main()
