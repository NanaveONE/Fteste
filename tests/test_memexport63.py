import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

P = Path(__file__).resolve().parents[1] / 'scripts/audit_memexport63_guest_writes.py'
spec = importlib.util.spec_from_file_location('mem63', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AuditTests(unittest.TestCase):
    def test_detects_direct_guest_memory_patterns(self):
        data = b'auto x = membase; PPC_STORE(x); memcpy(a,b,n); reinterpret_cast<int*>(x);'
        report = m.inspect([('fable_2_recomp.0.cpp', data)])
        self.assertEqual(report['potential_access_counts']['membase_references'], 1)
        self.assertEqual(report['potential_access_counts']['guest_store_helpers'], 1)
        self.assertEqual(report['potential_access_counts']['memory_intrinsics'], 1)
        self.assertFalse(report['memexport_commit_permitted'])
        self.assertNotIn('auto x = membase', str(report))

    def test_empty_fails(self):
        with self.assertRaises(ValueError):
            m.inspect([])

    def test_unrecognized_source_fails(self):
        with self.assertRaises(ValueError):
            m.inspect([('secret.cpp', b'hi')])

    def test_zero_hits_does_not_certify(self):
        r = m.inspect([('fable_2_init.cpp', b'int test = 1;')])
        self.assertFalse(r['global_exclusion_certified'])
        self.assertFalse(r['direct_guest_stores_fully_instrumented'])

    def test_zip_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / 'source.zip'
            with zipfile.ZipFile(z, 'w') as f:
                f.writestr('generated/default/fable_2_recomp.0.cpp', 'physical_membase;')
                f.writestr('README.txt', 'ignore')
            rows = m.read_sources(archive=z)
            self.assertEqual(len(rows), 1)
            self.assertEqual(m.inspect(rows)['translation_units'], 1)

    def test_duplicate_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / 'source.zip'
            with zipfile.ZipFile(z, 'w') as f:
                f.writestr('generated/default/fable_2_init.cpp', 'a')
                f.writestr('generated/default/fable_2_init.cpp', 'b')
            with self.assertRaises(ValueError):
                m.read_sources(archive=z)


if __name__ == '__main__':
    unittest.main()
