"""Host-side Memgate73 artifact gates (no game sources or NDK required)."""
from __future__ import annotations
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

spec = importlib.util.spec_from_file_location('package_memgate73_private',
                                              ROOT/'scripts/package_memgate73_private.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def reports():
    runtime = {'sdk_pin': mod.PIN, 'source_files': 3, 'scope_sites': 12,
               'commit_permitted': False}
    plume = {'stage': 72, 'status': 'PLUME_KNOWN_CPU_PATHS_ONLY_NOT_CERTIFIED',
             'source': {'plume_graphics_system.cpp':'a'*64,'plume_draw.cpp':'b'*64},
             'transformed': {'plume_graphics_system.cpp':'c'*64,'plume_draw.cpp':'d'*64},
             'registered_scope_sites': 7, 'vulkan_device_completion_covered': False,
             'all_dma_paths_covered': False, 'memexport_commit_permitted': False}
    shader = {'status': 'PRIVATE_ARM64_GPU_PROBE56_ONLY',
              'compiled': 583, 'expected': 588, 'missing': 5,
              'missing_hashes': mod.MISSING, 'production_approved': False,
              'guest_memexport_execution_proven': False}
    return runtime, plume, shader


def fake_elf(path: Path, payload: int, align: int = 16384):
    """Tiny ELF64 ET_DYN AArch64 with one valid PT_LOAD header."""
    body = bytearray(256)
    body[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<H', body, 16, 3)
    struct.pack_into('<H', body, 18, 183)
    struct.pack_into('<Q', body, 32, 64)
    struct.pack_into('<H', body, 54, 56)
    struct.pack_into('<H', body, 56, 1)
    struct.pack_into('<I', body, 64, 1)  # PT_LOAD
    struct.pack_into('<QQ', body, 72, 0, 0)
    struct.pack_into('<Q', body, 112, align)
    body[-1] = payload
    path.write_bytes(body)


class Memgate73Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def files(self):
        runtime = self.dir / 'runtime'
        runtime.mkdir()
        guest = self.dir / 'libfable2-Memgate71-DIAGNOSTICO.so'
        gpu = self.dir / mod.GPU
        gate = self.dir / mod.GATE
        for i, path in enumerate((guest, gpu, gate, *(runtime/name for name in (mod.RUNTIME, mod.CXX, mod.GATE)))):
            fake_elf(path, i + 1)
        reports_files = []
        for i, data in enumerate(reports()):
            p = self.dir / f'report{i}.json'
            p.write_text(json.dumps(data))
            reports_files.append(p)
        return guest, gate, gpu, runtime, *reports_files

    def test_accepted_only_known_incomplete_evidence(self):
        result = mod.check_evidence(*reports())
        self.assertEqual(result['shader_compiled'], 583)
        self.assertEqual(result['runtime_scope_sites'], 12)

    def test_reject_production_shader_or_guest_commit(self):
        r,p,s = reports()
        for data,key,value in ((r,'commit_permitted',True),
                               (p,'memexport_commit_permitted',True),
                               (p,'vulkan_device_completion_covered',True),
                               (s,'production_approved',True),
                               (s,'guest_memexport_execution_proven',True),
                               (s,'compiled',588)):
            copy = dict(data)
            copy[key] = value
            args = [dict(r),dict(p),dict(s)]
            args[(r,p,s).index(data)] = copy
            with self.subTest(key=key,value=value), self.assertRaises(mod.Blocked):
                mod.check_evidence(*args)

    def test_reject_drifted_pinned_sdk_or_plume_scopes(self):
        r,p,s = reports()
        for change in ({'sdk_pin': 'deadbeef'}, {'scope_sites': 1}, {'source_files': 2}):
            with self.assertRaises(mod.Blocked):
                mod.check_evidence({**r,**change},p,s)
        for change in ({'stage': 71}, {'registered_scope_sites': 6}, {'all_dma_paths_covered': True}):
            with self.assertRaises(mod.Blocked):
                mod.check_evidence(r,{**p,**change},s)

    def test_real_fake_arm64_elf_and_16k_alignment(self):
        p = self.dir / 'ok.so'
        fake_elf(p, 3)
        self.assertEqual(mod.ensure_elf(p)['min_pt_load_alignment'], 16384)
        fake_elf(p, 3, 4096)
        with self.assertRaises(mod.Blocked):
            mod.ensure_elf(p)

    def test_reject_symlink_and_corrupt_elf(self):
        target = self.dir/'regular.so'
        fake_elf(target, 6)
        link = self.dir/'link.so'
        link.symlink_to(target)
        with self.assertRaises(mod.Blocked):
            mod.ensure_elf(link)
        target.write_bytes(b'not ELF')
        with self.assertRaises(ValueError):
            mod.ensure_elf(target)

    def test_dynamic_dependency_regex_and_soname(self):
        sample = (' 0x0000000000000001 (NEEDED) Shared library: [libfable2_memgate71.so]\n'
                  ' 0x000000000000000e (SONAME) Library soname: [librexruntime.so]\n')
        with patch.object(mod.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=sample)):
            deps, soname = mod.dynamic(self.dir/'librexruntime.so','readelf')
        self.assertEqual(deps,{mod.GATE})
        self.assertEqual(soname,mod.RUNTIME)

    def test_dynamic_symbol_parser_excludes_undefined_imports(self):
        source = '''Symbol table '.dynsym' contains 3 entries:
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND fable_memgate71_enter
     2: 0000000000000120    12 FUNC    GLOBAL DEFAULT    7 fable_memgate71_leave
'''
        with patch.object(mod.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0,stdout=source)):
            result = mod.exported(self.dir/'libfable2_memgate71.so','readelf')
        self.assertEqual(result, {'fable_memgate71_leave'})

    def test_missing_private_lib_or_wrong_inventory(self):
        guest,gate,gpu,runtime,*_ = self.files()
        self.assertIn(mod.GATE,mod.inventory(runtime,guest,gate,gpu))
        (runtime/mod.CXX).unlink()
        with self.assertRaises(mod.Blocked):
            mod.inventory(runtime,guest,gate,gpu)
        fake_elf(runtime/'libburnout.so',9)
        with self.assertRaises(mod.Blocked):
            mod.inventory(runtime,guest,gate,gpu)

    def fake_dynamic(self, path: Path, tool: str):
        name = mod.GAME if path.name == 'libfable2-Memgate71-DIAGNOSTICO.so' else path.name
        needed = {mod.GATE} if name in (mod.GAME, mod.RUNTIME, mod.GPU) else set()
        if name in (mod.GAME,mod.GPU):
            needed.add(mod.RUNTIME)
        if name in (mod.GAME,mod.RUNTIME,mod.GPU):
            needed.add(mod.CXX)
        return needed,name

    def fake_exports(self, path: Path, tool: str):
        if path.name == mod.GATE:
            return set(mod.GATE_SYMBOLS)
        if path.name == mod.GPU:
            return {'rex_gpu_abi_version','rex_gpu_create'}
        if path.name in (mod.GAME, 'libfable2-Memgate71-DIAGNOSTICO.so'):
            return {'SDL_main'}
        return {'test'}

    def run_package(self, *args):
        with patch.object(mod, 'dynamic', side_effect=self.fake_dynamic), \
             patch.object(mod, 'exported', side_effect=self.fake_exports), \
             patch.object(mod, 'read_dynsym', return_value=({'fake'}, {'fake'})), \
             patch.object(mod, 'check_symbols',return_value={mod.GAME:{'rex_import_count':1,'rex_resolved_count':1},
                                                             mod.GPU:{'rex_import_count':1,'rex_resolved_count':1}}):
            return mod.package(*args)

    def test_success_bundle_has_single_gate_no_sources_and_no_apk(self):
        guest,gate,gpu,runtime,rr,pr,sr = self.files()
        dest = self.dir/'private73.zip'
        result = self.run_package(guest,gate,gpu,runtime,rr,pr,sr,dest,'readelf')
        self.assertTrue(dest.is_file())
        self.assertFalse(result['memexport_commit_permitted'])
        self.assertFalse(result['production_binary_approved'])
        self.assertFalse(result['apk_generated'])
        with ZipFile(dest) as z:
            libs = [p for p in z.namelist() if p.endswith('.so')]
            self.assertEqual(len(libs),5)
            self.assertEqual(sum(p.endswith('/'+mod.GATE) for p in libs),1)
            self.assertNotIn('private-generation.cpp',z.namelist())
            self.assertIn('diagnostic/memgate73.json',z.namelist())
            self.assertEqual(json.loads(z.read('diagnostic/memgate73.json'))['stage'],73)
        with self.assertRaises(mod.Blocked):
            self.run_package(guest,gate,gpu,runtime,rr,pr,sr,dest,'readelf')

    def test_reject_guest_runtime_or_gpu_missing_gate_link(self):
        guest,gate,gpu,runtime,rr,pr,sr = self.files()
        for target in (mod.GAME,mod.RUNTIME,mod.GPU):
            def broken(path,tool):
                deps,soname = self.fake_dynamic(path,tool)
                if soname == target:
                    deps.discard(mod.GATE)
                return deps,soname
            with self.subTest(target=target), \
                 patch.object(mod,'dynamic',side_effect=broken), \
                 patch.object(mod,'exported',side_effect=self.fake_exports), \
                 self.assertRaisesRegex(mod.Blocked,'missing shared gate'):
                mod.audit(mod.inventory(runtime,guest,gate,gpu),runtime/mod.GATE,'readelf')

    def test_reject_unresolved_dependency_and_missing_abi(self):
        guest,gate,gpu,runtime,rr,pr,sr = self.files()
        def missing(path,tool):
            deps,soname = self.fake_dynamic(path,tool)
            if path.name == mod.GPU: deps.add('libmissing_custom.so')
            return deps,soname
        with patch.object(mod,'dynamic',side_effect=missing), \
             patch.object(mod,'exported',side_effect=self.fake_exports), \
             self.assertRaisesRegex(mod.Blocked,'Unresolved native dependency'):
            mod.audit(mod.inventory(runtime,guest,gate,gpu),runtime/mod.GATE,'readelf')
        with patch.object(mod,'dynamic',side_effect=self.fake_dynamic), \
             patch.object(mod,'exported',return_value=set()), \
             self.assertRaisesRegex(mod.Blocked,'gate ABI exports missing'):
            mod.audit(mod.inventory(runtime,guest,gate,gpu),runtime/mod.GATE,'readelf')

    def test_readelf_errors_fail_closed(self):
        p = self.dir/'something.so'
        fake_elf(p,4)
        with patch.object(mod.subprocess,'run',return_value=types.SimpleNamespace(returncode=2,stdout='')):
            with self.assertRaises(mod.Blocked): mod.dynamic(p,'readelf')
            with self.assertRaises(mod.Blocked): mod.exported(p,'readelf')

    def test_workflow_private_only_and_actual_gpu_runtime_builds(self):
        wf = (ROOT/'.github/workflows/build-fable-memgate73-arm64-private.yml').read_text()
        for text in ('workflow_dispatch:', 'FABLE2_PRIVATE_TOKEN',
                     'FABLE2_MEMGATE71_DIAGNOSTIC:', 'build_rexglue_android_sdk.sh',
                     'build_fable_gpu.sh', 'FABLE2_GPU_PROBE56:',
                     'FABLE2_MEMGATE71_LIB:', 'package_memgate73_private.py',
                     'Fable2-Memgate73-ARM64-DIAGNOSTICO-PRIVADO.zip',
                     'gh release upload', 'if: failure()'):
            self.assertIn(text,wf)
        self.assertNotIn('actions/upload-artifact',wf)
        self.assertNotIn('FABLE2_MEMEXPORT_COMMIT_PERMITTED=1',wf)


if __name__ == '__main__':
    unittest.main()
