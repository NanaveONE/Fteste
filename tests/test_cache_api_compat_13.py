"""Regression for CI run logs_107980850568: v11 public API + v12 SMOL-V.

All examples are synthetic. No commercial game shader bytes are packaged.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.validate_xenosrecomp_cache import (
    CacheError, audit_cache, extract_cpp_cache, inspect_cpp, inspect_spirv,
)


def spirv_blob():
    return struct.pack('<5I', 0x07230203, 0x10500, 0, 20, 0) + struct.pack('<3I', (3 << 16) | 14, 0, 1)


def make_cache(shader_name='PS_test.bin', *, blob=None, names=None):
    blob = spirv_blob() if blob is None else blob
    names = [shader_name] if names is None else names
    compressed = subprocess.run(['zstd', '-q', '-c'], input=blob,
                                capture_output=True, check=True).stdout
    entries = '\n'.join(
        '{ 0x%x, 0, 0, 0, %s, 0, 0, 0, "shader/xenos-scan/%s" },'
        % (idx + 1, len(blob), name)
        for idx, name in enumerate(names)
    )
    return ('#include "shader_cache.h"\n'
            f'ShaderCacheEntry g_shaderCacheEntries[] = {{\n{entries}\n}};\n'
            'const size_t g_shaderCacheEntryCount = sizeof(g_shaderCacheEntries)/sizeof(g_shaderCacheEntries[0]);\n'
            'const uint8_t g_compressedSpirvCache[] = {'
            + ','.join(str(x) for x in compressed) + '};\n'
            + f'const size_t g_spirvCacheCompressedSize = {len(compressed)};\n'
            + f'const size_t g_spirvCacheDecompressedSize = {len(blob)};\n')


class CacheApiCompatTests(unittest.TestCase):
    def test_legacy_imports_and_raw_spirv(self):
        inspect_spirv(spirv_blob(), offset=0, size=len(spirv_blob()))
        entries, data, total = extract_cpp_cache(make_cache())
        self.assertEqual(len(entries), 1)
        self.assertEqual(total, len(spirv_blob()))
        self.assertGreater(len(data), 0)

    def test_bad_spirv_magic_and_word_count(self):
        with self.assertRaisesRegex(CacheError, 'magic'):
            inspect_spirv(b'\x00\x00\x00\x00' + spirv_blob()[4:], offset=0, size=len(spirv_blob()))
        with self.assertRaisesRegex(CacheError, 'word count'):
            inspect_spirv(spirv_blob()[:-4], offset=0, size=len(spirv_blob())-4)

    def test_empty_cache_rejected(self):
        with self.assertRaisesRegex(CacheError, 'EMPTY'):
            extract_cpp_cache(make_cache(names=[]))

    def test_legacy_audit_shows_missing_shaders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = root / 'scan'
            scan.mkdir()
            (scan / 'PS_test.bin').write_bytes(b'private fixture')
            cpp = root / 'shader_cache.cpp'
            cpp.write_text(make_cache())
            self.assertEqual(audit_cache(cpp, scan)['state'], 'PASS')
            (scan / 'VS_missing.bin').write_bytes(b'missing fixture')
            report = audit_cache(cpp, scan)
            self.assertEqual((report['compiled_containers'], report['missing_containers']), (1, 1))
            self.assertEqual(report['state'], 'INCOMPLETE')
            self.assertEqual(audit_cache(cpp, scan, required_coverage=.5)['state'], 'PASS')

    def test_unknown_or_duplicate_entries_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = root / 'scan'
            scan.mkdir()
            (scan / 'PS_test.bin').write_bytes(b'fixture')
            cpp = root / 'cache.cpp'
            cpp.write_text(make_cache(shader_name='PS_unknown.bin'))
            self.assertEqual(audit_cache(cpp, scan)['unmatched_cache_entries'], 1)
            cpp.write_text(make_cache(names=['PS_test.bin', 'PS_test.bin']))
            self.assertEqual(audit_cache(cpp, scan)['duplicate_cache_entries'], 1)
            self.assertEqual(audit_cache(cpp, scan)['state'], 'INCOMPLETE')

    def test_smol_v_does_not_claim_spirv_validation(self):
        # Construct a recognizable SMOL-V placeholder, not a real shader.
        # It must never be misclassified as ordinary SPIR-V.
        with self.assertRaisesRegex(CacheError, 'magic'):
            inspect_spirv(b'LOMS' + spirv_blob()[4:], offset=0, size=len(spirv_blob()))


if __name__ == '__main__':
    unittest.main()
