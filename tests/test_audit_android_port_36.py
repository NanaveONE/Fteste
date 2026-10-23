import importlib.util
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts/audit_android_port_36.py'
spec = importlib.util.spec_from_file_location('audit36', PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class Check(unittest.TestCase):
    def test_conditions(self):
        self.assertFalse(audit.condition('defined(_WIN32)'))
        self.assertTrue(audit.condition('!defined(_WIN32) && defined(__ANDROID__)'))
        self.assertFalse(audit.condition('defined(_WIN32) || !defined(ANDROID)'))
        self.assertIsNone(audit.condition('USE_D3D'))

    def test_transitive_and_guarded_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'src').mkdir()
            (root / 'src/main.cpp').write_text('#include "bridge.h"\n')
            (root / 'src/bridge.h').write_text('#ifdef _WIN32\n#include <windows.h>\n#else\n#include <thread>\n#endif\n')
            result = audit.scan(root)
            self.assertEqual(result['unguarded_windows_headers'], [])
            (root / 'src/bridge.h').write_text('#if defined(__ANDROID__)\n#include <windows.h>\n#endif\n')
            result = audit.scan(root)
            self.assertEqual(len(result['unguarded_windows_headers']), 1)

    def test_nested_else(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'src').mkdir()
            (root / 'src/main.cpp').write_text('#if defined(_WIN32)\n#include <windows.h>\n#else\n#if defined(__ANDROID__)\n#include <thread>\n#endif\n#endif\n')
            self.assertFalse(audit.scan(root)['unguarded_windows_headers'])

if __name__ == '__main__':
    unittest.main()
