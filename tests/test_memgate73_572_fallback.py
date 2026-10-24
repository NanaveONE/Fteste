"""Regressions for the 572 -> strict historical 583 diagnostic fallback.

All input shader containers here are synthetic and created in a temporary dir.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest
from zipfile import ZipFile

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('m73fixtures', TESTS/'test_memgate73_shader_reconcile.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
reconcile = base.module


class Fallback572Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = base.ShaderCacheTests(methodName='test_generated_583_pass_through_and_never_approves_commit')
        self.fixture.setUp()
        self.fixture.install_cache(self.fixture.as_cpp(self.fixture.old[:572]))

    def tearDown(self):
        self.fixture.tearDown()

    def verify(self, *, verifier=None):
        return self.fixture.run_reconcile(verifier)

    def test_exact_572_subset_restores_583_only_as_diagnostic(self):
        old = self.fixture.cache.read_bytes()
        result = self.verify()
        self.assertEqual(result['status'], 'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_572_SUBSET_MATCH')
        self.assertEqual(result['generated_entry_count'], 572)
        self.assertEqual(result['historical_entries_missing_from_generated'], 11)
        self.assertEqual(result['generated_entries_not_in_historical_583'], 0)
        self.assertTrue(result['safe_fallback_permitted'])
        self.assertFalse(result['memexport_commit_permitted'])
        self.assertFalse(result['shader_binary_equivalence_proven'])
        self.assertFalse(result['production_binary_approved'])
        self.assertEqual(self.fixture.cache.read_bytes(), self.fixture.old_cache)
        self.assertEqual((self.fixture.root/'shader_cache-generated73.cpp').read_bytes(), old)
        report = json.loads(self.fixture.report.read_text())
        self.assertEqual(report['memgate73_cache_fallback']['historical_extra_shaders_recovered'], 11)
        self.assertFalse(report['memgate73_cache_fallback']['five_new_MemExport_shaders_ignored'])

    def test_new_identity_not_present_in_historical_blocks(self):
        items = list(self.fixture.old[:572])
        shader_id, file_name = items[0]
        items[0] = (0xDEADBEEFDEADBEEF, file_name)
        source = self.fixture.as_cpp(items)
        self.fixture.install_cache(source)
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'not an exact subset'):
            self.verify()
        self.assertEqual(self.fixture.cache.read_bytes(), source)
        self.assertFalse((self.fixture.root/'shader_cache-generated73.cpp').exists())

    def test_one_changed_file_digest_even_if_id_matches_blocks(self):
        items=list(self.fixture.old[:572]); k,n=items[0]
        other = self.fixture.old[579][1]
        items[0]=(k,other)
        self.fixture.install_cache(self.fixture.as_cpp(items))
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'not an exact subset'):
            self.verify()

    def test_571_entries_not_authorized(self):
        partial=self.fixture.as_cpp(self.fixture.old[:571]);self.fixture.install_cache(partial)
        r=self.verify()
        self.assertEqual(r['status'],'BLOCKED_UNRECONCILED')
        self.assertFalse(r['safe_fallback_permitted'])
        self.assertEqual(self.fixture.cache.read_bytes(),partial)

    def test_sbks_tampered_blocked(self):
        self.fixture.banks[0].write_bytes(b'not same SHA')
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'SBK input'):
            self.verify()

    def test_historical_diagnostic_missing_blocked(self):
        with ZipFile(self.fixture.arch,'w') as z:
            z.writestr('diagnostic/memexport-43.json',json.dumps({'status':'no'}))
            z.writestr('partial-cache/shader_cache.cpp',self.fixture.old_cache)
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'diagnostic43'):
            self.verify()

    def test_invalid_historical_smolv_blocked_before_replacement(self):
        before=self.fixture.cache.read_bytes()
        def invalid(*args):
            raise reconcile.ReconcileBlocked('invalid zstd/SMOL-V')
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'invalid zstd/SMOL-V'):
            self.verify(verifier=invalid)
        self.assertEqual(self.fixture.cache.read_bytes(),before)

    def test_existing_backup_never_overwritten(self):
        backup=self.fixture.root/'shader_cache-generated73.cpp';backup.write_bytes(b'untouched')
        with self.assertRaisesRegex(reconcile.ReconcileBlocked,'preexisting'):
            self.verify()
        self.assertEqual(backup.read_bytes(),b'untouched')

    def test_full_588_path_still_strict(self):
        self.fixture.install_cache(self.fixture.as_cpp(self.fixture.all))
        r=self.verify()
        self.assertEqual(r['status'], 'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_588_COMPARISON')
        self.assertEqual(r['generated_entry_count'],588)
        self.assertTrue(r['safe_fallback_permitted'])
        self.assertFalse(r['memexport_commit_permitted'])


if __name__ == '__main__':
    unittest.main()
