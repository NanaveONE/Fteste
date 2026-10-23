import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

MOD = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze_fable_memexport_44.py'
spec = importlib.util.spec_from_file_location('memexport44', MOD)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample_zip(path, *, corrupt=False, missing_addr=False, count_error=False, unexpected_stage=False):
    failures = []
    sources = {}
    for i in range(5):
        h = f'{i+1:016X}'
        contents = (
            '#define g_ExportAddress g_VertexShaderConstants[8]\n'
            + ('[shader("pixel")]\n' if unexpected_stage else '[shader("vertex")]\n')
            + ('#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT\n'
               'output.oPos.xyzw = g_ExportAddress.xyzw;\n'
               if not missing_addr else '')
            + '#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT\n'
              'output.oPos.xyzw = float4(1.0, 2.0, 3.0, 4.0);\n'
        )
        payload = contents.encode()
        failures.append({'shader_hash': h, 'hlsl_sha256': hashlib.sha256(payload).hexdigest(),
                         'memexport_directives': 2 if not count_error else 3})
        sources[f'missing-hlsl/{h.lower()}.hlsl'] = payload
    data = {'total_shaders': 588, 'translated': 583, 'skipped': 5,
            'shader_failures': failures}
    with ZipFile(path, 'w') as z:
        z.writestr('diagnostic/memexport-43.json', json.dumps(data))
        for name, b in sources.items():
            z.writestr(name, b + (b'corrupted' if corrupt else b''))


class TestMemExport44(unittest.TestCase):
    def check_error(self, *, contains, **kwargs):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'diag.zip'
            sample_zip(p, **kwargs)
            with self.assertRaisesRegex(ValueError, contains):
                mod.analyze(p)

    def test_valid_synthetic_zip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'diag.zip'
            sample_zip(p)
            result = mod.analyze(p)
            self.assertEqual(result['compiled'], 583)
            self.assertEqual(result['memexport_instruction_count'], 10)
            self.assertEqual(result['memexport_address_writes'], 5)
            self.assertEqual(result['memexport_data_writes'], 5)
            self.assertEqual(result['shaders'][0]['streams'][0]['constant_register'], 8)

    def test_sha_mismatch_rejected(self):
        self.check_error(contains='Hash SHA-256 divergente', corrupt=True)

    def test_missing_memexport_address_rejected(self):
        self.check_error(contains='Quantidade de MemExport divergente', missing_addr=True)

    def test_instruction_count_mismatch_rejected(self):
        self.check_error(contains='Quantidade de MemExport divergente', count_error=True)

    def test_shader_stage_rejected(self):
        self.check_error(contains='nao e um vertex shader', unexpected_stage=True)

if __name__ == '__main__':
    unittest.main()
