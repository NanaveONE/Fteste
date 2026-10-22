import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.check_native_libs import REQUIRED, check, parse_needed


class NativeLibAuditTests(unittest.TestCase):
    def test_needed_parser(self):
        text = ' 0x0000000000000001 (NEEDED) Shared library: [libc++_shared.so]\n' \
               ' 0x0000000000000001 (NEEDED) Shared library: [librexruntime.so]'
        self.assertEqual(parse_needed(text), {'libc++_shared.so', 'librexruntime.so'})

    def test_rejects_burnout_binary_even_when_unused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'libmain_eu.so').write_bytes(b'not Fable')
            issues = check(base, 'llvm-readelf')
            self.assertTrue(any('Unrelated Burnout library' in issue for issue in issues))

    def test_rejects_absent_libs(self):
        with tempfile.TemporaryDirectory() as temp:
            errors = check(Path(temp), 'llvm-readelf')
        self.assertEqual(len(errors), len(REQUIRED))
        self.assertIn('libfable2.so', errors[0])

    def test_detects_missing_gpu_api(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in REQUIRED:
                (root / name).write_bytes(b'B' * 500)
            def fake_readelf(_, flag, path):
                if flag == '-h':
                    return ' Machine: AArch64'
                if flag == '-d':
                    return 'Dynamic section at offset\n'
                return 'Symbol table\n  12: 123 GLOBAL DEFAULT 10 rex_gpu_create SDL_main'
            with patch('scripts.check_native_libs.run_readelf', side_effect=fake_readelf):
                errors = check(root, 'llvm-readelf')
            self.assertEqual(len(errors), 1)
            self.assertIn('rex_gpu_abi_version', errors[0])

    def test_requires_android_sdl_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in REQUIRED:
                (root / name).write_bytes(b'B' * 500)
            def fake_readelf(_, flag, path):
                if flag == '-h': return ' Machine: AArch64'
                if flag == '-d': return ''
                return 'rex_gpu_create rex_gpu_abi_version'
            with patch('scripts.check_native_libs.run_readelf', side_effect=fake_readelf):
                issues = check(root, 'llvm-readelf')
            self.assertTrue(any('SDL_main not exported' in problem for problem in issues))

    def test_detects_burnout_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in REQUIRED:
                (root / name).write_bytes(b'B' * 500)
            def fake_readelf(_, flag, path):
                if flag == '-h': return ' Machine: AArch64'
                if flag == '-d': return '(NEEDED) Shared library: [libmain_eu.so]'
                return 'rex_gpu_create rex_gpu_abi_version SDL_main'
            with patch('scripts.check_native_libs.run_readelf', side_effect=fake_readelf):
                errors = check(root, 'llvm-readelf')
            self.assertEqual(len(errors), len(REQUIRED))
            self.assertIn('libmain_eu.so', errors[0])


if __name__ == '__main__':
    unittest.main()
