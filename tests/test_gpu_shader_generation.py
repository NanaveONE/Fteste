import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.generate_fable_shaders import cache_is_usable, create_cache
from scripts.gpu_log_report import summarize


CACHE = '''#include <cstddef>
struct ShaderCacheEntry {unsigned long long hash;};
ShaderCacheEntry g_shaderCacheEntries[1]{{0x1234}};
const size_t g_shaderCacheEntryCount = 1;
const unsigned char g_compressedSpirvCache[2] = {1,2};
const size_t g_spirvCacheCompressedSize = 2;
struct ShaderMicrocodeEntry {unsigned long long hash;};
ShaderMicrocodeEntry g_shaderMicrocodeEntries[1]{{0x1234}};
const size_t g_shaderMicrocodeEntryCount = 1;
'''


class ShaderPipelineTests(unittest.TestCase):
    def test_cache_rejects_empty(self):
        self.assertFalse(cache_is_usable(CACHE.replace('g_shaderCacheEntryCount = 1', 'g_shaderCacheEntryCount = 0')))
        self.assertFalse(cache_is_usable(CACHE.replace('g_spirvCacheCompressedSize = 2', 'g_spirvCacheCompressedSize = 0')))
        self.assertFalse(cache_is_usable('x'))
        self.assertTrue(cache_is_usable(CACHE))

    def test_generates_shader_cache_from_guest_image_without_game_assets_in_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guest = root / 'owned_guest_image.bin'
            guest.write_bytes(b'FAKE-DECODED-IMAGE-TEST-FIXTURE')
            header = root / 'shader_common.h'
            header.write_text('// fixture\n')
            tool = root / 'fake-recompiler'
            tool.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
pathlib.Path(sys.argv[2]).write_text(''' + repr(CACHE) + ''')
pathlib.Path(os.environ['XENOS_RECOMP_DUMP_SOURCE_DIR'], '0123456789ABCDEF.hlsl').write_text('void main() {}')
''')
            tool.chmod(0o755)
            output = root / 'build' / 'fable2-shaders'
            result = create_cache(None, guest, output, None, tool, header)
            self.assertEqual(result['hlsl_files'], 1)
            self.assertEqual(result['source_title'], 'Fable II')
            self.assertTrue((output / 'shader_cache.cpp').is_file())
            self.assertFalse((output / 'default.xex').exists())
            self.assertEqual(json.loads((output / 'fable-shader-report.json').read_text())['hlsl_hashes'], ['0123456789ABCDEF'])
            with self.assertRaisesRegex(ValueError, 'Output exists'):
                create_cache(None, guest, output, None, tool, header)

    def test_rejects_fake_xex(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            xex = root / 'default.xex'
            xex.write_bytes(b'wrong')
            header = root / 'header.h'
            header.write_text('')
            tool = root / 'tool'
            tool.write_text('#!/bin/sh\nexit 0\n')
            tool.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'not XEX2'):
                create_cache(xex, None, root / 'out', tool, tool, header)

    def test_gpu_log_categories(self):
        data = ['plume: IM_LOAD VS ucode=0123456789ABCDEF cache MISS',
                'plume: createShader failed for cache entry 0123456789ABCDEF',
                'plume: rejected draw',
                'random other text']
        result = summarize(data)
        self.assertEqual(result['gpu_issue_counts']['missing_shader'], 1)
        self.assertEqual(result['gpu_issue_counts']['gpu_error'], 1)
        self.assertEqual(result['gpu_issue_counts']['rejected_draw'], 1)
        self.assertEqual(result['shader_or_pipeline_hashes']['missing_shader']['0123456789abcdef'], 1)

    def test_cmake_uses_fable_cache_not_burnout_game(self):
        text = (Path(__file__).parents[1] / 'port/gpu/CMakeLists.txt').read_text()
        self.assertIn('FABLE2_SHADER_CACHE_CPP', text)
        self.assertIn('shader_source_info_gen.cpp', text)
        self.assertIn('add_library(rexgpu-plume SHARED', text)
        self.assertNotIn('add_library(burnout', text)
        self.assertNotIn('GPU_PLUGINS xenos', text)


if __name__ == '__main__':
    unittest.main()
