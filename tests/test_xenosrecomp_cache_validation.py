"""Validate generated-cache inspection using SYNTHETIC SPIR-V, no game data."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from scripts.validate_xenosrecomp_cache import (
    CacheError, audit_cache, extract_cpp_cache, inspect_spirv,
)


def spirv_blob():
    return struct.pack('<5I', 0x07230203, 0x10500, 0, 20, 0) + struct.pack('<3I', (3 << 16) | 14, 0, 1)


def make_cpp(*, names=('PS_test.bin',), spv=None):
    spv = spv if spv is not None else spirv_blob()
    compressed = subprocess.run(['zstd', '-q', '-c'], input=spv, capture_output=True, check=True).stdout
    entries = '\n'.join(
        f'{{ 0x{n+1:x}, 0, 0, 0, {len(spv)}, 0, 0, 0, "shader/xenos-scan/{name}" }},'
        for n, name in enumerate(names))
    return (f'#include "shader_cache.h"\n'
            f'ShaderCacheEntry g_shaderCacheEntries[] = {{\n{entries}\n}};\n'
            f'const size_t g_shaderCacheEntryCount = sizeof(g_shaderCacheEntries)/sizeof(g_shaderCacheEntries[0]);\n'
            f'const uint8_t g_compressedSpirvCache[] = {{' + ','.join(str(b) for b in compressed) + '};\n'
            f'const size_t g_spirvCacheCompressedSize = {len(compressed)};\n'
            f'const size_t g_spirvCacheDecompressedSize = {len(spv)};\n')


class XenosOutputTests(unittest.TestCase):
    def test_spirv_valid_structure(self):
        blob = spirv_blob()
        inspect_spirv(blob, offset=0, size=len(blob))

    def test_spirv_rejects_wrong_magic_and_truncated_instruction(self):
        with self.assertRaisesRegex(CacheError, 'magic'):
            inspect_spirv(b'\0\0\0\0' + spirv_blob()[4:], offset=0, size=len(spirv_blob()))
        broken = spirv_blob()[:-4]
        with self.assertRaisesRegex(CacheError, 'word count'):
            inspect_spirv(broken, offset=0, size=len(broken))

    def test_empty_cache_rejected(self):
        with self.assertRaisesRegex(CacheError, 'EMPTY'):
            extract_cpp_cache(make_cpp(names=()))

    def test_match_real_cpp_layout(self):
        entries, blob, size = extract_cpp_cache(make_cpp())
        self.assertEqual(len(entries), 1)
        self.assertEqual(size, len(spirv_blob()))
        self.assertGreater(len(blob), 10)

    def test_cache_matches_private_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / 'scan'
            scan.mkdir()
            (scan / 'PS_test.bin').write_bytes(b'test-fixture')
            cpp = root / 'shader_cache.cpp'
            cpp.write_text(make_cpp())
            out = audit_cache(cpp, scan)
            self.assertEqual(out['state'], 'PASS')
            self.assertEqual(out['compiled_pixel_shaders'], 1)
            self.assertEqual(out['coverage_percent'], 100.0)

    def test_uncompiled_shader_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / 'scan'
            scan.mkdir()
            (scan / 'PS_test.bin').write_bytes(b'test-fixture')
            (scan / 'VS_missing.bin').write_bytes(b'test-fixture')
            cpp = root / 'shader_cache.cpp'
            cpp.write_text(make_cpp())
            report = audit_cache(cpp, scan)
            self.assertEqual(report['state'], 'INCOMPLETE')
            self.assertEqual(report['missing_containers'], 1)
            self.assertEqual(report['coverage_percent'], 50.0)
            self.assertEqual(audit_cache(cpp, scan, required_coverage=0.5)['state'], 'PASS')

    def test_fake_cache_entry_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / 'scan'
            scan.mkdir()
            (scan / 'PS_test.bin').write_bytes(b'test-fixture')
            cpp = root / 'shader_cache.cpp'
            cpp.write_text(make_cpp(names=('PS_unknown.bin',)))
            self.assertEqual(audit_cache(cpp, scan)['unmatched_cache_entries'], 1)
            cpp.write_text(make_cpp(names=('PS_test.bin', 'PS_test.bin')))
            self.assertEqual(audit_cache(cpp, scan)['duplicate_cache_entries'], 1)


if __name__ == '__main__':
    unittest.main()
