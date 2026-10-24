"""Synthetic Memgate73 shader mismatch diagnostics. No proprietary game inputs."""
from __future__ import annotations
import importlib.util
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/reconcile_memgate73_shader_cache.py'
spec = importlib.util.spec_from_file_location('memgate73_reconcile',SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

HASHES = sorted(module.MISSING)

def digest(blob): return hashlib.sha256(blob).hexdigest()

class ShaderCacheTests(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory()
        self.root = Path(self.ctx.name)
        self.scan = self.root/'xenos-scan';self.scan.mkdir()
        self.cache = self.root/'shader_cache.cpp'
        self.report = self.root/'fable-shader-report.json'
        self.arch = self.root/'private43.zip'
        self.banks=[]
        for i,name in enumerate(('Shaders.sbk','ShadersRelease.sbk')):
            b=self.root/name;b.write_bytes(b'private-synthetic-'+bytes([i]))
            self.banks.append(b)
        self.old=[];self.all=[]
        # The historical approved set is 132 VS + 451 PS.
        for i in range(588):
            extra=i>=583
            if extra:
                stage='VS';id=HASHES[i-583]
            else:
                stage='VS' if i<132 else 'PS';id=i+1
            blob=b'synthetic shader container '+str(i).encode()
            name=f'{stage}_{digest(blob)}.bin'
            (self.scan/name).write_bytes(blob)
            item=(id,name)
            self.all.append(item)
            if not extra:self.old.append(item)
        self.current=self.all
        self.old_cache=self.as_cpp(self.old)
        self.install_cache(self.as_cpp(self.current))
        diag={'status':'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED','total_shaders':588,'translated':583,'skipped':5,
              'shader_failures':[{'shader_hash':f'{x:016X}','hlsl_found':True} for x in HASHES]}
        with ZipFile(self.arch,'w') as z:
            z.writestr('diagnostic/memexport-43.json',json.dumps(diag))
            z.writestr('partial-cache/shader_cache.cpp',self.old_cache)

    def tearDown(self):self.ctx.cleanup()
    @staticmethod
    def as_cpp(items):
        rows=[f'{{ 0x{num:016X}, 0, 0, 0, 32, 0, 0, 0, "{name}" }},' for num,name in items]
        return ('ShaderCacheEntry g_shaderCacheEntries[] = {\n'+'\n'.join(rows)+'\n};\n').encode()
    def install_cache(self, blob):
        self.cache.write_bytes(blob)
        r={'source_title':'Fable II','input_kind':'shader_banks','extracted_containers':588,
           'cache_sha256':digest(blob),'shader_banks':[{'filename':b.name,'sha256':module.file_sha(b)} for b in self.banks]}
        self.report.write_text(json.dumps(r))

    def run_reconcile(self,verify=None):
        if verify is None:
            def verify(path,scan):
                self.assertEqual(path.read_bytes(),self.old_cache)
                self.assertEqual(scan,self.scan)
        return module.reconcile(self.cache,self.report,self.scan,self.banks,self.arch,verify_original=verify)

    def test_generated_583_pass_through_and_never_approves_commit(self):
        self.install_cache(self.old_cache)
        result=self.run_reconcile()
        self.assertEqual(result['generated_entry_count'],583)
        self.assertEqual(result['status'],'KEEP_GENERATED_583_VALIDATE_WITH_PROBE56')
        self.assertFalse(result['memexport_commit_permitted'])
        self.assertEqual(self.cache.read_bytes(),self.old_cache)
        self.assertFalse((self.root/'shader_cache-generated73.cpp').exists())

    def test_exact_588_reuses_prior_583_only_when_five_extra_match(self):
        before=self.cache.read_bytes()
        result=self.run_reconcile()
        self.assertEqual(result['generated_entry_count'],588)
        self.assertTrue(result['safe_fallback_permitted'])
        self.assertFalse(result['production_binary_approved'])
        self.assertEqual(self.cache.read_bytes(),self.old_cache)
        self.assertEqual((self.root/'shader_cache-generated73.cpp').read_bytes(),before)
        record=json.loads(self.report.read_text())
        self.assertEqual(record['cache_sha256'],digest(self.old_cache))
        self.assertFalse(record['memgate73_cache_fallback']['production_approved'])
        self.assertTrue(record['memgate73_cache_fallback']['five_new_MemExport_shaders_ignored'])

    def test_other_number_is_diagnosed_not_substituted(self):
        blob=self.as_cpp(self.all[:-1]);self.install_cache(blob)
        result=self.run_reconcile()
        self.assertEqual(result['generated_entry_count'],587)
        self.assertEqual(result['status'],'BLOCKED_UNRECONCILED')
        self.assertEqual(self.cache.read_bytes(),blob)

    @unittest.skipUnless(ctypes.util.find_library('zstd') and
                         (SCRIPT.parent/'validate_xenosrecomp_cache.py').is_file(),
                         'Real cache inspector/libzstd unavailable in isolated tests')
    def test_strict_original_real_zstd_smol_validation(self):
        # End-to-end test: use the real previous-stage SMOL-V cache inspector,
        # not a mocked verification function. Synthetic module headers only.
        raw = (b'LOMS' + bytes(16)) * 583
        lib = ctypes.CDLL(ctypes.util.find_library('zstd'))
        lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
        lib.ZSTD_compressBound.restype = ctypes.c_size_t
        lib.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        lib.ZSTD_compress.restype = ctypes.c_size_t
        lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        lib.ZSTD_isError.restype = ctypes.c_uint
        dst=ctypes.create_string_buffer(lib.ZSTD_compressBound(len(raw)))
        src=ctypes.create_string_buffer(raw)
        count=lib.ZSTD_compress(dst,len(dst),src,len(raw),1)
        self.assertEqual(lib.ZSTD_isError(count),0)
        blob=dst.raw[:count]
        lines=[f'{{ 0x{num:016X}, 0, 0, {i*20}, 20, 0, 0, 0, "{name}" }},'
               for i,(num,name) in enumerate(self.old)]
        c=('ShaderCacheEntry g_shaderCacheEntries[] = {\n'+'\n'.join(lines)+'\n};\n'
           +'uint8_t g_compressedSpirvCache[] = {'+', '.join(str(n) for n in blob)+'};\n'
           +f'const size_t g_spirvCacheDecompressedSize = {len(raw)};\n'
           +f'const size_t g_spirvCacheCompressedSize = {len(blob)};\n').encode()
        self.old_cache=c
        diag={'status':'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED',
              'total_shaders':588,'translated':583,'skipped':5,
              'shader_failures':[{'shader_hash':f'{x:016X}','hlsl_found':True}
                                 for x in HASHES]}
        with ZipFile(self.arch,'w') as z:
            z.writestr('diagnostic/memexport-43.json',json.dumps(diag))
            z.writestr('partial-cache/shader_cache.cpp',c)
        result=module.reconcile(self.cache,self.report,self.scan,self.banks,self.arch)
        self.assertTrue(result['safe_fallback_permitted'])
        self.assertEqual(self.cache.read_bytes(),c)

    def test_extra_id_changed_rejected_even_if_count_588(self):
        current=list(self.all);current[-1]=(0xBADC0DE,current[-1][1])
        blob=self.as_cpp(current);self.install_cache(blob)
        with self.assertRaisesRegex(module.ReconcileBlocked,'five MemExport'):
            self.run_reconcile()
        self.assertEqual(self.cache.read_bytes(),blob)

    def test_extra_stage_changed_rejected(self):
        # Keep source-file digest genuine; change new entry's stage to PS.
        current=list(self.all);num,name=current[-1];current[-1]=(num,name.replace('VS_','PS_',1))
        self.install_cache(self.as_cpp(current))
        with self.assertRaisesRegex(module.ReconcileBlocked,'does not match SBK'):
            self.run_reconcile()

    def test_missing_input_sha_rejected_before_touching_cache(self):
        self.banks[0].write_bytes(b'tampered')
        before=self.cache.read_bytes()
        with self.assertRaisesRegex(module.ReconcileBlocked,'SBK input'):
            self.run_reconcile()
        self.assertEqual(self.cache.read_bytes(),before)

    def test_corrupt_source_payload_rejected(self):
        next(self.scan.iterdir()).write_bytes(b'tampered')
        with self.assertRaisesRegex(module.ReconcileBlocked,'differs'):
            self.run_reconcile()

    def test_historical_report_rejected_if_five_hashes_change(self):
        with ZipFile(self.arch,'w') as z:
            z.writestr('diagnostic/memexport-43.json',json.dumps({'status':'OK'}))
            z.writestr('partial-cache/shader_cache.cpp',self.old_cache)
        with self.assertRaisesRegex(module.ReconcileBlocked,'diagnostic43'):
            self.run_reconcile()

    def test_historical_583_compressed_validation_required(self):
        def fail_verify(cache,scan):
            raise module.ReconcileBlocked('historical SMOL-V failed')
        before=self.cache.read_bytes()
        with self.assertRaisesRegex(module.ReconcileBlocked,'historical SMOL-V'):
            self.run_reconcile(fail_verify)
        self.assertEqual(self.cache.read_bytes(),before)
        self.assertFalse((self.root/'shader_cache-generated73.cpp').exists())

    def test_no_clobber_of_untrusted_generated_backup(self):
        marker=self.root/'shader_cache-generated73.cpp';marker.write_bytes(b'EXISTING')
        with self.assertRaisesRegex(module.ReconcileBlocked,'preexisting'):
            self.run_reconcile()
        self.assertEqual(marker.read_bytes(),b'EXISTING')

    def test_identity_duplicate_and_malformed_blocked(self):
        for c in (self.as_cpp(self.all[:5]+self.all[:1]),b'ShaderCacheEntry g_shaderCacheEntries[] = {junk};'):
            with self.subTest(kind=len(c)),self.assertRaises(module.ReconcileBlocked):
                module.entries(c)

    def test_all_paths_are_build_only_and_workflow_privacy(self):
        wf=(SCRIPT.parents[1]/'.github/workflows/build-fable-memgate73-arm64-private.yml').read_text()
        self.assertIn('reconcile_memgate73_shader_cache.py',wf)
        self.assertIn('cache-reconcile.json',wf)
        self.assertNotIn('actions/upload-artifact@',wf)
        self.assertIn('memexport_commit_permitted',SCRIPT.read_text())

if __name__=='__main__':unittest.main()
