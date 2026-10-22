"""Synthetic GDFX tests and safe patch tests: no proprietary game input."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.enable_fable_iso_install import (LAUNCHER, EXTRACTOR, INSTALLER,
                                             REPLACEMENTS, patch)

REPO = Path(__file__).resolve().parents[1]


class IsoReaderTests(unittest.TestCase):
    def test_synthetic_gdfx_reader_and_security(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'classes'
            out.mkdir()
            files = [REPO / EXTRACTOR,
                     REPO / 'tests/java/Fable2IsoExtractorTest.java']
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(out),
                            *(str(f) for f in files)], check=True,
                           capture_output=True, text=True)
            result = subprocess.run(['java', '-cp', str(out),
                                     'com.nanaveone.fable2.Fable2IsoExtractorTest'],
                                    capture_output=True, text=True, check=True)
            self.assertIn('PASS: 10 GDFX', result.stdout)

    def test_android_installer_transaction_with_saf_stubs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'classes'
            out.mkdir()
            root = REPO / 'tests/java'
            sources = [REPO / EXTRACTOR, REPO / INSTALLER,
                       *sorted(root.rglob('*.java'))]
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(out),
                            *(str(f) for f in sources)], check=True,
                           capture_output=True, text=True)
            result = subprocess.run(['java', '-cp', str(out),
                                     'com.nanaveone.fable2.Fable2IsoInstallerTest'],
                                    capture_output=True, text=True, check=True)
            self.assertIn('PASS: transactional ISO installer', result.stdout)


class InstallerPatchTests(unittest.TestCase):
    def fixture(self, folder: Path):
        launcher = folder / LAUNCHER
        launcher.parent.mkdir(parents=True, exist_ok=True)
        # Include all source anchors without containing any output anchors.
        pieces = []
        for before, _ in REPLACEMENTS:
            pieces.append(before)
            if before.startswith('                    importButton.setEnabled(true);'):
                pieces.append(before)
        launcher.write_text('before\n' + '\n__SEP__\n'.join(pieces) + '\nafter')
        for dependency in (EXTRACTOR, INSTALLER):
            file = folder / dependency
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('// fixture')

    def test_patch_applies_atomically_and_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            self.assertEqual(patch(root), 'updated')
            self.assertEqual(patch(root), 'verified')
            self.assertEqual(patch(root, check=True), 'verified')
            java = (root / LAUNCHER).read_text()
            self.assertIn('PICK_GAME_ISO = 43', java)
            self.assertIn('Fable2IsoInstaller.install(', java)
            self.assertIn('PICK_GAME_FOLDER = 42', java)

    def test_check_refuses_unapplied_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'ainda não aplicada'):
                patch(root, check=True)

    def test_unknown_upstream_source_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            target = root / LAUNCHER
            target.write_text('different upstream version')
            with self.assertRaisesRegex(ValueError, 'launcher diferente'):
                patch(root)
            self.assertEqual(target.read_text(), 'different upstream version')

    def test_missing_dependency_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / EXTRACTOR).unlink()
            with self.assertRaisesRegex(ValueError, 'ausente'):
                patch(root)


if __name__ == '__main__':
    unittest.main()

class UpstreamExtractorTests(unittest.TestCase):
    def test_catalog_identifies_goty_and_refuses_unknown_xex(self):
        from scripts.extract_fable_iso_upstream import validate_xex, validate_data
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xex = root / 'default.xex'
            xex.write_bytes(b'XEX2-fixture')
            import hashlib
            catalog = root / 'versions.json'
            catalog.write_text(json.dumps({'versions': [{'hash': hashlib.sha256(xex.read_bytes()).hexdigest(),
                                    'xexSize': xex.stat().st_size, 'compatible': True,
                                    'id': 'goty-fixture', 'requiredFiles': ['data/gold_version.txt'],
                                    'rejectFiles': ['data/tu1_data.bnk']}] }))
            profile = validate_xex(xex, catalog)
            self.assertEqual(profile['id'], 'goty-fixture')
            data = root / 'data'
            data.mkdir()
            with self.assertRaisesRegex(ValueError, 'obrigatório'):
                validate_data(root, profile)
            (data / 'gold_version.txt').write_text('fixture')
            validate_data(root, profile)
            (data / 'tu1_data.bnk').write_text('fixture')
            with self.assertRaisesRegex(ValueError, 'incompatível'):
                validate_data(root, profile)
            xex.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'não contém'):
                validate_xex(xex, catalog)
