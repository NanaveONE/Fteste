import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from install_memexport70_private_guest import install, Blocked
from instrument_memexport66_guest_writes import _read_archive

CAS = b'''#include <cstdint>
void guest_writer(unsigned long ea) {
  auto ok = __sync_bool_compare_and_swap(
    reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), 1u, 2u);
  (void)ok;
}
'''
MEM = b'''#include <cstring>
void guest_memory(void* ea, void* buf) {
  memcpy(REX_RAW_ADDR(ea), buf, 8);
}
'''


class Memexport70Tests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'build').mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix='m70-test-', dir=ROOT / 'build'))
        self.worktree = self.tmp / 'fable2-android-worktree'
        self.generated = self.worktree / 'generated/default'
        self.generated.mkdir(parents=True)
        self.sources = {
            'fable_2_recomp.0.cpp': CAS,
            'fable_2_init.cpp': MEM,
        }
        for name, body in self.sources.items():
            (self.generated / name).write_bytes(body)
        (self.generated / 'codegen.build.stamp').write_text('private imported C++')
        (self.generated / 'sources.cmake').write_text('set(GENERATED_SOURCES\n' + ''.join(
            '  "${CMAKE_CURRENT_LIST_DIR}/' + n + '"\n' for n in self.sources) + ')\n')
        self.archive = self.tmp / 'private-cpp.zip'
        with ZipFile(self.archive, 'w') as z:
            for name, body in self.sources.items():
                z.writestr('generated/default/' + name, body)
        _sources, self.hash = _read_archive(self.archive)
        self.report = self.tmp / 'memexport70-result.json'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_install(self, **kw):
        return install(self.archive, self.generated, self.report,
                       expected_source_sha256=self.hash,
                       expected_translation_units=2,
                       expected_atomics=1, expected_intrinsics=1, **kw)

    def test_rewrite_installed_atomically_and_keeps_non_cpp_files(self):
        before = (self.generated / 'sources.cmake').read_bytes()
        r = self.run_install()
        self.assertEqual(r['atomic_calls_wrapped'], 1)
        self.assertEqual(r['memory_intrinsics_wrapped'], 1)
        self.assertFalse(r['memexport_commit_permitted'])
        self.assertFalse(r['production_binary_approved'])
        self.assertTrue(self.report.is_file())
        self.assertEqual((self.generated / 'sources.cmake').read_bytes(), before)
        self.assertIn(b'ObserveWrite', (self.generated / 'fable_2_recomp.0.cpp').read_bytes())
        self.assertIn(b'ObserveWrite', (self.generated / 'fable_2_init.cpp').read_bytes())
        self.assertTrue((self.generated / 'fable_memexport_writer66.h').is_file())
        self.assertTrue((self.generated / 'codegen.build.stamp').is_file())
        self.assertFalse((self.generated.parent / '.memexport70-backup-default').exists())
        self.assertNotIn('guest_writer', self.report.read_text())

    def test_reject_unexpected_private_archive_content_before_modifying(self):
        (self.generated / 'fable_2_init.cpp').write_bytes(b'other source')
        with self.assertRaisesRegex(Blocked, 'changed since verified'):
            self.run_install()
        self.assertEqual((self.generated / 'fable_2_recomp.0.cpp').read_bytes(), CAS)
        self.assertFalse(self.report.exists())

    def test_reject_bad_source_index(self):
        (self.generated / 'sources.cmake').write_text('set(GENERATED_SOURCES)')
        with self.assertRaisesRegex(Blocked, 'source index'):
            self.run_install()

    def test_reject_wrong_expected_count_before_modifying(self):
        with self.assertRaisesRegex(Blocked, 'drift'):
            install(self.archive, self.generated, self.report,
                    expected_source_sha256=self.hash,
                    expected_translation_units=2,
                    expected_atomics=8436, expected_intrinsics=1)
        self.assertEqual((self.generated / 'fable_2_recomp.0.cpp').read_bytes(), CAS)
        self.assertFalse(self.report.exists())

    def test_termux_missing_os_link_uses_copy2(self):
        # Some Android/Termux Python builds expose no os.link attribute.
        # The replacement tree must still be complete and validated.
        with patch.object(os, 'link', None, create=True):
            report = self.run_install()
        self.assertEqual(report['atomic_calls_wrapped'], 1)
        self.assertIn(b'ObserveWrite', (self.generated / 'fable_2_recomp.0.cpp').read_bytes())
        self.assertTrue((self.generated / 'sources.cmake').is_file())
        self.assertFalse((self.generated.parent / '.memexport70-backup-default').exists())

    def test_hardlink_not_supported_uses_copy2(self):
        with patch.object(os, 'link', side_effect=OSError(errno.EOPNOTSUPP,
                                                          'unsupported'), create=True):
            report = self.run_install()
        self.assertEqual(report['memory_intrinsics_wrapped'], 1)
        self.assertTrue((self.generated / 'codegen.build.stamp').is_file())

    def test_unexpected_hardlink_io_error_fails_without_swapping(self):
        with patch.object(os, 'link', side_effect=OSError(errno.EIO,
                                                          'I/O failure'), create=True):
            with self.assertRaises(OSError):
                self.run_install()
        self.assertEqual((self.generated / 'fable_2_recomp.0.cpp').read_bytes(), CAS)
        self.assertFalse(self.report.exists())
        self.assertFalse((self.generated.parent / '.memexport70-backup-default').exists())

    def test_reject_stale_run(self):
        self.run_install()
        with self.assertRaisesRegex(Blocked, 'Report already exists'):
            self.run_install()

    def test_reject_symlinked_source(self):
        p = self.generated / 'fable_2_init.cpp'
        p.unlink()
        p.symlink_to(self.generated / 'fable_2_recomp.0.cpp')
        with self.assertRaises(Blocked):
            self.run_install()

    def test_reject_destinations_outside_private_build(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            with self.assertRaisesRegex(Blocked, 'Fteste/build'):
                install(self.archive, Path(elsewhere), self.report,
                        expected_translation_units=2, expected_atomics=1,
                        expected_intrinsics=1)

    def test_reject_report_collision_with_archive(self):
        with self.assertRaisesRegex(Blocked, 'must not overwrite'):
            install(self.archive, self.generated, self.archive,
                    expected_translation_units=2, expected_atomics=1,
                    expected_intrinsics=1)

    def test_reject_non_generated_destination(self):
        wrong = self.tmp / 'other'
        wrong.mkdir()
        with self.assertRaisesRegex(Blocked, 'generated/default'):
            install(self.archive, wrong, self.report,
                    expected_translation_units=2, expected_atomics=1,
                    expected_intrinsics=1)

    def test_ci_diagnostic_binary_kept_separate(self):
        workflow = (ROOT/'.github/workflows/build-fable2-arm64-26.yml').read_text()
        self.assertIn('memexport70_diagnostic:', workflow)
        self.assertIn('libfable2-MemExport70-DIAGNOSTICO.so', workflow)
        self.assertIn('Fable2-MemExport70-AMOSTRAS-PRIVADAS.txt', workflow)
        self.assertIn('Fable2-MemExport70-CONTEXTOS-PRIVADO.json', workflow)
        self.assertIn('else\n            gh release upload "$RELEASE_TAG"', workflow)
        self.assertNotIn('actions/upload-artifact@', workflow)

    def test_reject_stale_backup(self):
        backup = self.generated.parent / '.memexport70-backup-default'
        backup.mkdir()
        with self.assertRaisesRegex(Blocked, 'interrupted'):
            self.run_install()

    def test_cli_failure_does_not_leak_private_source(self):
        p = subprocess.run([sys.executable,
                            str(ROOT / 'scripts/install_memexport70_private_guest.py'),
                            '--archive', str(self.archive),
                            '--generated-dir', str(self.generated),
                            '--report', str(self.report),
                            '--expected-translation-units', '297'],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn('guest_writer', p.stderr)
        self.assertFalse(self.report.exists())


if __name__ == '__main__':
    unittest.main()
