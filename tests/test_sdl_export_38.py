import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_fable2_sdl_export_38 import check, EXPORTED_ENTRY
from enable_fable2_sdl_export_38 import patch, OLD, NEW


class TestSdlExport38(unittest.TestCase):
    def test_defined_export_and_many_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lib = base / "libfable2.so"
            lib.write_bytes(b"not-a-real-elf-for-mocked-readelf")
            tool = base / "llvm-readelf"
            tool.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('Symbol table .dynsym')\n"
                "print('  14: 0000000000193000  123 FUNC    GLOBAL DEFAULT   12 SDL_main')\n"
                "for i in range(30000):\n"
                " print(f' {i+100}: 00000000 0 FUNC GLOBAL DEFAULT 12 other_{i}')\n"
            )
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            ok, message = check(lib, tool)
            self.assertTrue(ok, message)

    def test_missing_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lib = base / "libfable2.so"
            lib.write_bytes(b"x")
            tool = base / "llvm-readelf"
            tool.write_text("#!/bin/sh\nprintf '%s\\n' ' 9: 00 22 FUNC GLOBAL DEFAULT UND SDL_main'\n")
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            ok, message = check(lib, tool)
            self.assertFalse(ok)
            self.assertIn("UND SDL_main", message)

    def test_hidden_export_is_rejected(self):
        self.assertIsNone(EXPORTED_ENTRY.search(
            "  19: 00000 0 FUNC GLOBAL HIDDEN 14 SDL_main"))
        self.assertIsNone(EXPORTED_ENTRY.search(
            "  19: 00000 0 FUNC LOCAL DEFAULT 14 SDL_main"))

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "build_android_native.sh"
            p.write_text("#!/bin/bash\n" + OLD + "\n")
            self.assertEqual(patch(p), "patched")
            self.assertEqual(patch(p), "already applied")
            self.assertIn(NEW, p.read_text())
            self.assertNotIn(OLD, p.read_text())

    def test_unknown_version_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "build_android_native.sh"
            p.write_text("#!/bin/bash\nother code\n")
            with self.assertRaises(ValueError):
                patch(p)
            self.assertEqual(p.read_text(), "#!/bin/bash\nother code\n")


if __name__ == "__main__":
    unittest.main()
