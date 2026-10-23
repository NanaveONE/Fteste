import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'

def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

report = load('report_fable_memexport_43')
enable = load('enable_shader_diagnostics_43')

class MemexportDiagnostics(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)
        self.hlsl = self.root / 'hlsl'
        self.hlsl.mkdir()
        self.hlsl.joinpath('17A0FEDEF93DAE25.hlsl').write_text('#error ' + report.MEMEXPORT)
        self.log = 'Found 588 raw shader containers\n' + (report.MEMEXPORT + '\n') * 2 + 'DXC SPIR-V failed for shader 17A0FEDEF93DAE25; skipping\nWrote 587 unique shaders (1 skipped)\n'
        self.cache = self.root / 'shader_cache.cpp'
        self.cache.write_text('X'*200)
    def tearDown(self):
        self.t.cleanup()
    def test_extract_missing(self):
        data, sources=report.make_report(self.log, self.hlsl, self.cache)
        self.assertEqual(data['translated'], 587)
        self.assertEqual(data['skipped'], 1)
        self.assertEqual(len(sources), 1)
    def test_reject_mismatch(self):
        with self.assertRaises(ValueError):
            report.make_report(self.log.replace('587 unique', '588 unique'), self.hlsl, self.cache)
    def test_reject_unrecognized_errors(self):
        with self.assertRaises(ValueError):
            report.make_report(self.log.replace(report.MEMEXPORT, 'MISSING_TYPE'), self.hlsl, self.cache)
    def test_archive_private_diagnostics(self):
        log=self.root/'translator.log';log.write_text(self.log)
        dest=self.root/'diag.zip'
        report.create(log, self.cache, self.hlsl, dest)
        with ZipFile(dest) as z:
            self.assertIn('missing-hlsl/17A0FEDEF93DAE25.hlsl',z.namelist())
            self.assertIn('diagnostic/memexport-43.json', z.namelist())
            self.assertIn('partial-cache/shader_cache.cpp', z.namelist())
    def test_workflow_patch_anchors(self):
        source=enable.OLD + '      - name: Verificar cobertura completa do cache Vulkan\n' + '      - name: Compactar resultado para armazenamento privado\n'
        first=enable.transform(source)
        self.assertIn('tee build/shader-translation-43.log', first)
        self.assertIn('if: failure()', first)
        self.assertIn('gh release upload', first)
        self.assertEqual(enable.transform(first), first)

if __name__=='__main__':
    unittest.main()
