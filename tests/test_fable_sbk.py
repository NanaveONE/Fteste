"""Only synthetic binaries: never publish user-supplied Fable II shader banks."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from scripts.extract_fable_sbk import MAGIC, parse_bank, extract_banks
from scripts.find_fable_shader_banks import locate
from scripts.generate_fable_shaders import create_cache


CACHE_FIXTURE = '''#include <cstddef>
struct ShaderCacheEntry { unsigned long long hash; };
ShaderCacheEntry g_shaderCacheEntries[1]{{0x1234}};
const size_t g_shaderCacheEntryCount = 1;
const unsigned char g_compressedSpirvCache[1] = {1};
const size_t g_spirvCacheCompressedSize = 1;
struct ShaderMicrocodeEntry { unsigned long long hash; };
ShaderMicrocodeEntry g_shaderMicrocodeEntries[1]{{0x1234}};
const size_t g_shaderMicrocodeEntryCount = 1;
'''


def example_bank(*, minor: int = 0, pixel: bool = True) -> bytes:
    flags = 0x102A1100 if pixel else 0x102A1101
    container = struct.pack('>9I', flags, 36, 12, 0, 36, 0, 36, 0, 0) + b'\x00' * 12
    payload = struct.pack('>5I', 20, 0, 20, 20, 20) + container
    compressor = zlib.compressobj(level=9)
    compressed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
    assert compressed.endswith(b'\x00\x00\xff\xff')
    return MAGIC + bytes((0, 3, minor, 0)) + b'metadata-ignored' + len(compressed).to_bytes(4, 'big') + compressed


class SBKBankTests(unittest.TestCase):
    def test_parses_valid_pixel_and_vertex_containers(self):
        a = parse_bank(example_bank(minor=1, pixel=True))
        b = parse_bank(example_bank(minor=0, pixel=False))
        self.assertEqual((a.version, a.compressed_blocks, len(a.shaders), a.shaders[0].stage),
                         ('0x0301', 1, 1, 'PS'))
        self.assertEqual((b.version, b.shaders[0].stage), ('0x0300', 'VS'))

    def test_rejects_incorrect_magic(self):
        with self.assertRaisesRegex(ValueError, 'ShaderBankFile'):
            parse_bank(b'Broken' + example_bank()[6:])

    def test_rejects_unsupported_version(self):
        corrupted = bytearray(example_bank())
        corrupted[17] = 5
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            parse_bank(bytes(corrupted))

    def test_rejects_truncated_data(self):
        with self.assertRaisesRegex(ValueError, 'Could not find complete'):
            parse_bank(example_bank()[:-1])

    def test_writes_unique_containers_without_bank_assets_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / 'Shaders.sbk', root / 'ShadersRelease.sbk'
            a.write_bytes(example_bank(minor=1))
            b.write_bytes(example_bank(minor=0))
            result = extract_banks([a, b], root / 'build/sbk')
            self.assertEqual(result['unique_containers'], 1)
            self.assertEqual(result['duplicate_containers_across_banks'], 1)
            files = list((root / 'build/sbk/xenos-scan').glob('*.bin'))
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].name.startswith('PS_'))
            self.assertNotIn('metadata-ignored', (root / 'build/sbk/sbk-analysis.json').read_text())
            with self.assertRaisesRegex(ValueError, 'Output already exists'):
                extract_banks([a], root / 'build/sbk')

    def test_locate_case_insensitive_banks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / 'data/ShAdErS'
            d.mkdir(parents=True)
            p = d / 'SHADERS.sbk'
            p.write_bytes(example_bank())
            self.assertEqual(locate(root), [p])
            (d / 'Shaders.sbk').write_bytes(example_bank())
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                locate(root)

    def test_end_to_end_bank_cache_path_using_stub_translator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bank = root / 'ShadersRelease.sbk'
            bank.write_bytes(example_bank())
            header = root / 'shader_common.h'
            header.write_text('// fixture')
            tool = root / 'fake-translator'
            tool.write_text('#!/usr/bin/env python3\nimport pathlib,sys\n'
                            'assert len(list(pathlib.Path(sys.argv[1]).glob("PS_*.bin"))) == 1\n'
                            'pathlib.Path(sys.argv[2]).write_text(' + repr(CACHE_FIXTURE) + ')\n')
            tool.chmod(0o755)
            result = create_cache(None, None, root / 'build/shaders', None, tool, header,
                                  shader_banks=[bank])
            self.assertEqual(result['input_kind'], 'shader_banks')
            self.assertEqual(result['extracted_containers'], 1)
            self.assertEqual(len(result['shader_banks']), 1)
            self.assertTrue((root / 'build/shaders/shader_cache.cpp').is_file())
            self.assertEqual(json.loads((root / 'build/shaders/fable-shader-report.json').read_text())['extracted_containers'], 1)

    def test_build_script_uses_sbk_not_xex_only(self):
        source = (Path(__file__).parents[1] / 'scripts/attempt_playable_build.sh').read_text()
        self.assertIn('--shader-banks', source)
        self.assertIn('find_fable_shader_banks.py', source)
        self.assertNotIn('--game-xex "$FABLE2_GAME_ROOT/default.xex"', source)


if __name__ == '__main__':
    unittest.main()
