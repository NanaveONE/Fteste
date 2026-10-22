import stat
import tempfile
import unittest
from pathlib import Path

from scripts.compile_fable_runtime_shaders import read_capture, compile_captures
from scripts.merge_fable_shader_sources import merge


class CapturedShaderTests(unittest.TestCase):
    def capture(self, folder, stage='VS', args='--element 0:1:2'):
        stem = f'{stage}_1234567890ABCDEF_12'
        (folder / (stem + '.wrapargs')).write_text('# scanner derived metadata\n' + args + '\n')
        (folder / (stem + '.bin')).write_bytes(b'\x01' * 12)

    def executable(self, folder, name, body):
        file = folder / name
        file.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n' + body + '\n')
        file.chmod(file.stat().st_mode | stat.S_IXUSR)
        return file

    def test_capture_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            captures = Path(tmp)
            self.capture(captures)
            parsed = read_capture(captures)
            self.assertEqual(parsed[0][0], 'VS')
            self.assertEqual(parsed[0][2], ['--element', '0:1:2'])
            (captures / 'VS_1234567890ABCDEF_12.bin').write_bytes(b'x' * 10)
            with self.assertRaisesRegex(ValueError, 'size invalid'):
                read_capture(captures)

    def test_reject_unsupported_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            captures = Path(tmp)
            self.capture(captures, 'PS', '--element 0:1:2')
            with self.assertRaisesRegex(ValueError, 'Unexpected shader declaration'):
                read_capture(captures)

    def test_offline_runtime_pipeline_uses_bootstrap_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captures = root / 'captures'
            captures.mkdir()
            self.capture(captures)
            guest = root / 'guest.bin'
            guest.write_bytes(b'MZ' + b'\0' * 62)
            header = root / 'shader_common.h'
            header.write_text('// real header required outside test')
            # These tiny programs are interface test doubles, not a claim
            # about the Xenos translator's output or Fable rendering.
            rehost = self.executable(root, 'rehost', 'sys.exit(1)')
            wrap_vs = self.executable(root, 'wrap_vs', 'Path(sys.argv[2]).write_bytes(b"CONTAINER")')
            wrap_ps = self.executable(root, 'wrap_ps', 'Path(sys.argv[2]).write_bytes(b"CONTAINER")')
            translator = self.executable(root, 'translator', 'Path(sys.argv[2]).write_text("original")')
            symbols = ['g_shaderCacheEntriesBootstrap', 'g_shaderCacheEntryCountBootstrap',
                       'g_compressedSpirvCacheBootstrap', 'g_spirvCacheCompressedSizeBootstrap',
                       'g_shaderMicrocodeEntriesBootstrap', 'g_shaderMicrocodeEntryCountBootstrap']
            rename = self.executable(root, 'rename',
                                     'Path(sys.argv[2]).write_text(' + repr(' '.join(symbols)) + ')')
            result = compile_captures(captures, root / 'out', guest, translator, header,
                                      rehost, wrap_vs, wrap_ps, rename)
            self.assertEqual(result['capture_count'], 1)
            self.assertEqual(result['rehosted_count'], 0)
            self.assertTrue((root / 'out/shader_cache_runtime.cpp').exists())
            with self.assertRaisesRegex(ValueError, 'Output exists'):
                compile_captures(captures, root / 'out', guest, translator, header,
                                 rehost, wrap_vs, wrap_ps, rename)

    def test_metadata_merging_detects_hash_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static, runtime = root / 'static', root / 'runtime'
            static.mkdir()
            runtime.mkdir()
            (static / '1234567890ABCDEF.hlsl').write_text('static shader')
            (runtime / '1234567890ABCDEF.hlsl').write_text('different shader')
            with self.assertRaisesRegex(ValueError, 'disagree'):
                merge(static, runtime, root / 'merged')
            (runtime / '1234567890ABCDEF.hlsl').write_text('static shader')
            (runtime / 'FEDCBA0987654321.hlsl').write_text('dynamic shader')
            report = merge(static, runtime, root / 'merged')
            self.assertEqual(report['merged_hlsl'], 2)

if __name__ == '__main__':
    unittest.main()
