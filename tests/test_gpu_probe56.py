"""Public tests; no game files or proprietary shader bytes."""
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

def read_module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

probe = read_module('scripts/validate_gpu_probe56.py', 'probe56')
installer = read_module('scripts/enable_fable_gpu_probe56.py', 'installer56')


def evidence():
    cache = b'FAKE-SYNTHETIC-CACHE-FOR-TEST-ONLY'
    banks = [{'filename': n, 'sha256': 'a'*64} for n in
             ('Shaders.sbk', 'ShadersRelease.sbk')]
    report = {'source_title': 'Fable II', 'input_kind': 'shader_banks',
              'extracted_containers': 588,
              'cache_sha256': hashlib.sha256(cache).hexdigest(), 'shader_banks': banks}
    diag = {'status': 'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED',
            'total_shaders': 588, 'translated': 583, 'skipped': 5,
            'shader_failures': [{'shader_hash': h, 'hlsl_found': True}
                                for h in sorted(probe.KNOWN_MISSING)]}
    stats = {'state': 'INCOMPLETE', 'expected': 588, 'compiled': 583,
             'missing': 5, 'vertex': 132, 'pixel': 451,
             'unmatched': 0, 'duplicate': 0}
    return cache,report,diag,stats


class ProbeTests(unittest.TestCase):
    def test_strict_evidence_passes_and_is_not_production(self):
        cache, report, diag, stats = evidence()
        result = probe.validate_evidence(cache, report, diag, cache, stats)
        self.assertEqual(result['compiled'], 583)
        self.assertEqual(len(result['missing_hashes']), 5)
        self.assertFalse(result['production_approved'])
        self.assertFalse(result['guest_memexport_execution_proven'])

    def test_reject_every_scope_expansion(self):
        cache, report, diag, stats = evidence()
        for mutation in ('title', 'source', 'count', 'hash', 'banks', 'bank_hash',
                         'diagnostic_missing', 'diagnostic_hash', 'shader_stage',
                         'unsupported', 'duplicate', 'drift'):
            import copy
            r,d,s = copy.deepcopy(report), copy.deepcopy(diag), copy.deepcopy(stats)
            old=cache
            if mutation=='title':r['source_title']='Burnout Revenge'
            if mutation=='source':r['input_kind']='decoded_guest_image'
            if mutation=='count':r['extracted_containers']=587
            if mutation=='hash':r['cache_sha256']='0'*64
            if mutation=='banks':r['shader_banks']=[]
            if mutation=='bank_hash':r['shader_banks'][0]['sha256']='bad'
            if mutation=='diagnostic_missing':d['skipped']=4
            if mutation=='diagnostic_hash':d['shader_failures'][0]['shader_hash']='1234567890ABCDEF'
            if mutation=='shader_stage':s['vertex']=133
            if mutation=='unsupported':s['state']='PASS'
            if mutation=='duplicate':s['duplicate']=1
            if mutation=='drift':old=b'different-cpp-cache'
            with self.subTest(mutation=mutation),self.assertRaises(probe.ProbeError):
                probe.validate_evidence(cache,r,d,old,s)

    def test_read_only_zip_and_diagnostic_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache,report,diag,stats=evidence()
            directory=root/'xenos-scan';directory.mkdir()
            (root/'shader_cache.cpp').write_bytes(cache)
            (root/'fable-shader-report.json').write_text(json.dumps(report))
            zippath=root/'private-43.zip'
            with ZipFile(zippath,'w') as z:
                z.writestr('diagnostic/memexport-43.json',json.dumps(diag))
                z.writestr('partial-cache/shader_cache.cpp',cache)
            original=probe.inspect_cpp
            seen_thresholds=[]
            def fake_inspect(*args, **kwargs):
                seen_thresholds.append(kwargs.get('min_coverage'))
                return stats
            probe.inspect_cpp=fake_inspect
            try:
                result=probe.validate(root/'shader_cache.cpp',directory,root/'fable-shader-report.json',zippath)
            finally:
                probe.inspect_cpp=original
            self.assertEqual(result['expected'],588)
            self.assertEqual(seen_thresholds,[1.0])
            self.assertFalse((root/'gpu-probe56-report.json').exists())

    def test_opt_in_installer_and_unchanged_strict_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'scripts').mkdir()
            f=root/'scripts/build_fable_gpu.sh'
            f.write_text('#!/usr/bin/env bash\nFABLE2_PLUME_55_BUILDSCRIPT\n'+installer.BEFORE+'\n'+installer.ALIGN_BEFORE+'\n')
            with self.assertRaises(ValueError):installer.run(root,True)
            installer.run(root,False)
            installer.run(root,True)
            s=f.read_text()
            self.assertIn('FABLE2_GPU_PROBE56_OPT_IN',s)
            self.assertIn('--min-coverage 1.0',s)
            self.assertIn('FABLE2_GPU_PROBE56:-0',s)
            self.assertIn('FABLE2_GPU_DIAGNOSTIC43_ZIP',s)
            self.assertIn('ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON',s)
            self.assertIn('max-page-size=16384',s)
            installer.run(root,False)
            self.assertEqual(f.read_text().count(installer.MARK),1)
            f.write_text(s.replace('--min-coverage 1.0','--min-coverage 0.1'))
            with self.assertRaises(ValueError):installer.run(root,True)
            f.write_text(s.replace('max-page-size=16384','max-page-size=4096'))
            with self.assertRaises(ValueError):installer.run(root,True)

    def test_unknown_gpu_builder_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'scripts').mkdir()
            f=root/'scripts/build_fable_gpu.sh';f.write_text('NOT_RECOGNIZED')
            with self.assertRaises(ValueError):installer.run(root,False)
            self.assertEqual(f.read_text(),'NOT_RECOGNIZED')

if __name__=='__main__':unittest.main()
