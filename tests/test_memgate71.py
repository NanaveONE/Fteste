"""Memgate71 host ABI, cross-DSO concurrency, opt-in SDK/CMake tests.
No Fable II proprietary data is needed. Not a gameplay validation.
"""
from __future__ import annotations
import ctypes
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'port/sdk'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

patch_sdk = load('patch_rex_memgate71_sdk')
patch_guest = load('install_memgate71_guest_cmake')


class Snap(ctypes.Structure):
    _fields_ = [('abi_version', ctypes.c_uint32), ('struct_size', ctypes.c_uint32),
                ('entries', ctypes.c_uint64 * 5),
                ('active_outer_writers', ctypes.c_uint64),
                ('exclusive_diagnostic_acquires', ctypes.c_uint64),
                ('blocked_entries', ctypes.c_uint64),
                ('diagnostic_exclusive_active', ctypes.c_uint32),
                ('all_writers_certified', ctypes.c_uint32),
                ('memexport_commit_permitted', ctypes.c_uint32),
                ('reserved', ctypes.c_uint32)]


@unittest.skipUnless(shutil.which('g++') or shutil.which('clang++'),
                     'C++ compiler unavailable')
class GateABITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('clang++')
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        subprocess.run([compiler, '-std=c++20', '-shared', '-fPIC', '-O2', '-pthread',
                        '-Wall', '-Wextra', '-Werror', '-I', str(SDK),
                        str(SDK/'fable_memgate71.cpp'), '-o',
                        str(cls.work/'libfable2_memgate71.so')], check=True, capture_output=True)
        for name in ('guest', 'runtime'):
            src = cls.work / (name + '.cpp')
            src.write_text('''#include "fable_memgate71.h"
extern "C" int enter_writer(unsigned k) { return fable_memgate71_enter(k); }
extern "C" int leave_writer(unsigned k) { return fable_memgate71_leave(k); }
extern "C" int snapshot(FableMemgate71Snapshot* s) {
 return fable_memgate71_snapshot(s, sizeof(*s)); }
''')
            subprocess.run([compiler, '-std=c++20', '-shared', '-fPIC', '-O2',
                            '-Wl,-rpath,$ORIGIN', '-I', str(SDK), str(src),
                            '-L', str(cls.work), '-lfable2_memgate71', '-o',
                            str(cls.work/(name+'.so'))], check=True, capture_output=True)
        cls.gate = ctypes.CDLL(str(cls.work/'libfable2_memgate71.so'))
        cls.guest = ctypes.CDLL(str(cls.work/'guest.so'))
        cls.runtime = ctypes.CDLL(str(cls.work/'runtime.so'))
        for obj in (cls.guest, cls.runtime):
            obj.enter_writer.argtypes = [ctypes.c_uint]
            obj.leave_writer.argtypes = [ctypes.c_uint]
            obj.snapshot.argtypes = [ctypes.POINTER(Snap)]
        cls.gate.fable_memgate71_acquire_diagnostic.argtypes = [ctypes.c_uint]
        cls.gate.fable_memgate71_snapshot.argtypes = [ctypes.POINTER(Snap), ctypes.c_uint]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def snapshot(self):
        s = Snap()
        self.assertEqual(self.gate.fable_memgate71_snapshot(ctypes.byref(s), ctypes.sizeof(s)), 1)
        return s

    def test_two_dsos_share_one_counter_and_prohibit_commits(self):
        base = self.snapshot().entries[0]
        self.assertEqual(self.guest.enter_writer(0), 1)
        try:
            s = Snap()
            self.assertEqual(self.runtime.snapshot(ctypes.byref(s)), 1)
            self.assertEqual(s.active_outer_writers, 1)
            self.assertEqual(s.entries[0], base + 1)
            self.assertEqual(s.all_writers_certified, 0)
            self.assertEqual(s.memexport_commit_permitted, 0)
            self.assertEqual(self.gate.fable_memgate71_commit_permitted(), 0)
            self.assertEqual(self.gate.fable_memgate71_acquire_diagnostic(1), 0)
        finally:
            self.assertEqual(self.guest.leave_writer(0), 1)

    def test_nested_guest_operation_does_not_deadlock(self):
        self.assertEqual(self.runtime.enter_writer(0), 1)
        try:
            self.assertEqual(self.guest.enter_writer(1), 1)
            self.assertEqual(self.snapshot().active_outer_writers, 1)
            self.assertEqual(self.guest.leave_writer(1), 1)
        finally:
            self.assertEqual(self.runtime.leave_writer(0), 1)
        self.assertEqual(self.snapshot().active_outer_writers, 0)

    def test_exclusive_blocks_new_outer_writer_and_owner_releases(self):
        self.assertEqual(self.gate.fable_memgate71_acquire_diagnostic(100), 1)
        started = threading.Event()
        finished = threading.Event()
        def enter():
            started.set()
            if self.runtime.enter_writer(2) == 1:
                self.runtime.leave_writer(2)
            finished.set()
        thread = threading.Thread(target=enter)
        thread.start()
        try:
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.05))
            self.assertEqual(self.snapshot().diagnostic_exclusive_active, 1)
            self.assertEqual(self.gate.fable_memgate71_commit_permitted(), 0)
        finally:
            self.assertEqual(self.gate.fable_memgate71_release_diagnostic(), 1)
            thread.join(2)
        self.assertTrue(finished.is_set())
        self.assertEqual(self.snapshot().active_outer_writers, 0)

    def test_exclusive_owner_cannot_reenter_and_deadlock(self):
        self.assertEqual(self.gate.fable_memgate71_acquire_diagnostic(20), 1)
        try:
            self.assertEqual(self.guest.enter_writer(0), 0)
            self.assertEqual(self.gate.fable_memgate71_commit_permitted(), 0)
        finally:
            self.assertEqual(self.gate.fable_memgate71_release_diagnostic(), 1)

    def test_malformed_kind_and_snapshot_are_rejected(self):
        self.assertEqual(self.guest.enter_writer(99), 0)
        self.assertEqual(self.guest.leave_writer(99), 0)
        self.assertEqual(self.gate.fable_memgate71_snapshot(None, ctypes.sizeof(Snap)), 0)
        self.assertEqual(self.gate.fable_memgate71_snapshot(ctypes.byref(Snap()), 0), 0)

    def test_guest_writer66_header_links_only_with_opt_in(self):
        source = self.work / 'observer.cpp'
        source.write_text('''#include "fable_memexport_writer66.h"
#include <cstdint>
extern "C" uint32_t observer(uint32_t* ptr) {
 return fable2::memexport66::ObserveWrite(fable2::memexport66::Kind::Atomic,
   [&]() { return __sync_fetch_and_add(ptr, 1u); });
}
''')
        compiler = shutil.which('g++') or shutil.which('clang++')
        cmd = [compiler, '-std=c++20', '-shared', '-fPIC', '-pthread', '-O2',
               '-DFABLE2_MEMGATE71_DIAGNOSTIC=1', '-I', str(SDK),
               str(source), '-L', str(self.work), '-Wl,-rpath,$ORIGIN',
               '-lfable2_memgate71', '-o', str(self.work/'observer.so')]
        subprocess.run(cmd, check=True, capture_output=True)
        obj = ctypes.CDLL(str(self.work/'observer.so'))
        obj.observer.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
        before = self.snapshot().entries[1]
        val = ctypes.c_uint32(2)
        self.assertEqual(obj.observer(ctypes.byref(val)), 2)
        self.assertEqual(val.value, 3)
        self.assertEqual(self.snapshot().entries[1], before + 1)


class IntegrationTests(unittest.TestCase):
    THREAD = '#include <rex/system/xthread.h>\nvoid XThread::Execute() {\n  real();\n}\n'
    MEMORY = ('#include <rex/system/xmemory.h>\n'
              'void Memory::Zero(uint32_t address, uint32_t size) {\n  real();\n}\n'
              'void Memory::Fill(uint32_t address, uint32_t size, uint8_t value) {\n  real();\n}\n'
              'void Memory::Copy(uint32_t dest, uint32_t src, uint32_t size) {\n  real();\n}\n')

    def test_runtime_scope_anchors_and_opt_in(self):
        for path, code in [('src/system/xthread.cpp', self.THREAD),
                           ('src/system/xmemory.cpp', self.MEMORY)]:
            generated = patch_sdk.modify(path, code)
            self.assertIn('FABLE2_MEMGATE71_COOPERATIVE_SCOPE', generated)
            self.assertIn('#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)', generated)
            self.assertIn('WriterScope', generated)
            with self.assertRaises(ValueError):
                patch_sdk.modify(path, generated)

    def test_scope_wrong_anchor_fails(self):
        with self.assertRaises(ValueError):
            patch_sdk.modify('src/system/xthread.cpp', 'unknown sdk')

    def test_sdk_pin_and_opt_in_cmake(self):
        with tempfile.TemporaryDirectory() as td:
            sdk = Path(td)
            for p, c in [(k, self.THREAD if 'xthread' in k else self.MEMORY)
                         for k in patch_sdk.SITES]:
                f = sdk / p
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(c)
            (sdk/'CMakeLists.txt').write_text('project(sdk)\n')
            with patch.object(patch_sdk.subprocess, 'check_output', return_value=patch_sdk.PIN+'\n'):
                self.assertEqual(patch_sdk.patch(sdk)['scope_sites'], 4)
                self.assertEqual(patch_sdk.patch(sdk, check=True)['scope_sites'], 4)
                with self.assertRaises(ValueError): patch_sdk.patch(sdk)
            self.assertIn('target_link_libraries(rexruntime PRIVATE fable2_memgate71)',
                          (sdk/'CMakeLists.txt').read_text())

    def test_guest_cmake_rejected_outside_build_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(ValueError):
                patch_guest.install(base)
        # Worktree needs build/ element, as in the real Android build.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'build/fable2-android-worktree'
            p.mkdir(parents=True)
            cmake = p/'CMakeLists.txt'
            cmake.write_text('project(fake)\nadd_library(fable_2 SHARED ${FABLE2_SOURCES})\n')
            patch_guest.install(p)
            patch_guest.install(p, check=True)
            with self.assertRaises(ValueError): patch_guest.install(p.parent.parent)
            self.assertEqual(cmake.read_text().count(patch_guest.MARK), 1)

    def test_abi_checker_rejects_unlinked_or_host_elf(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from check_memgate71_abi import inspect, elf_aarch64, read_dynamic
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / 'fake.so'
            a.write_bytes(b'not an AArch64 shared library')
            self.assertFalse(elf_aarch64(a))
            with self.assertRaisesRegex(ValueError, 'AArch64'):
                inspect(a, a, 'llvm-readelf')

    def test_no_gpu_commits_and_public_artifacts(self):
        self.assertIn('return 0;', (SDK/'fable_memgate71.cpp').read_text())
        self.assertIn('all_writers_certified = 0', (SDK/'fable_memgate71.cpp').read_text())
        wf = (ROOT/'.github/workflows/build-fable2-arm64-26.yml').read_text()
        self.assertIn('memgate71_diagnostic:', wf)
        self.assertNotIn('actions/upload-artifact@', wf)

if __name__ == '__main__':
    unittest.main()
