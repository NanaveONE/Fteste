"""Verify the Android catalog against the pinned recomp upstream and Java parser."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_JAVA = ROOT / 'port/android/java/com/nanaveone/fable2/Fable2GameCompatibility.java'
UPSTREAM = ROOT / 'external/Fable-2-Recomp/constants/game_versions.json'


class AndroidCatalogTest(unittest.TestCase):
    def test_catalog_values_have_valid_sha256_and_no_unverified_profiles(self):
        source = CATALOG_JAVA.read_text(encoding='utf-8')
        profiles = re.findall(r'new Profile\("([^\"]+)", "([0-9a-f]{64})", (true|false)\)', source)
        self.assertEqual(len(profiles), 6)
        self.assertEqual(len({x[0] for x in profiles}), len(profiles))
        self.assertIn(('goty-us-eu',
                       '88c4ef2e18e65409444d1b068eff921d1f7e180a5ae64edc64ba6b0872372662',
                       'false'), profiles)
        self.assertNotIn('goty-latin-america', [x[0] for x in profiles])
        if UPSTREAM.is_file():
            data = json.loads(UPSTREAM.read_text(encoding='utf-8'))
            upstream = {v['id']:v for v in data['versions'] if v['compatible']}
            self.assertEqual({p[0] for p in profiles}, set(upstream))
            for ident, sha, _ in profiles:
                self.assertEqual(upstream[ident]['hash'], sha)
                self.assertEqual(upstream[ident]['xexSize'], 21217280)

    def test_java_catalog_compiles_and_rejects_invalid_dump(self):
        if not shutil.which('javac') or not shutil.which('java'):
            self.skipTest('JDK unavailable')
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            launcher = folder / 'Runner.java'
            launcher.write_text('''package com.nanaveone.fable2;
import java.io.*;
class Runner {
  public static void main(String[] args) throws Exception {
    try { Fable2GameCompatibility.checkXex(new ByteArrayInputStream(new byte[]{1,2,3}));
          throw new AssertionError("Invalid file was accepted"); }
    catch (IOException expected) {}
    File root = new File(args[0], "fake_game");
    File data = new File(root, "data");
    if (!data.mkdirs()) throw new IOException("mkdir");
    new File(root, "default.xex").createNewFile();
    try { Fable2GameCompatibility.checkData(root,
      new Fable2GameCompatibility.Profile("goty-us-eu", "dummy", false));
          throw new AssertionError("Missing files were accepted"); }
    catch (IOException expected) {}
  }
}''', encoding='utf-8')
            compiler = subprocess.run(['javac','--release','17','-d',str(folder),str(CATALOG_JAVA),str(launcher)],
                                      capture_output=True,text=True)
            self.assertEqual(compiler.returncode,0,compiler.stderr)
            run = subprocess.run(['java','-cp',str(folder),'com.nanaveone.fable2.Runner',str(folder)],
                                 capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_transactional_import_does_not_modify_installed_game_while_copying(self):
        source = (ROOT / 'port/android/java/com/nanaveone/fable2/Fable2LauncherActivity.java').read_text()
        self.assertIn('game.pending', source)
        self.assertIn('game.backup', source)
        self.assertIn('Fable2GameCompatibility.checkXex(source)', source)
        self.assertIn('Fable2GameCompatibility.checkData(staging, profile)', source)
        self.assertIn('staging.renameTo(gameRoot)', source)
        self.assertNotIn('copyDocument(tree, item, gameRoot', source)


if __name__ == '__main__':
    unittest.main()
