import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from inspect_memexport69_opaque_shapes import SHAPES, audit, classify_opaque_body, main
from classify_memexport67_raw_addresses import read_inputs


class MemExport69Tests(unittest.TestCase):
    def classify(self, code):
        counts, examples = classify_opaque_body(code.encode())
        return counts

    def test_nested_cas_excluded(self):
        c = self.classify('ctx.cr0.eq=__sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), 0, 1);')
        self.assertEqual(sum(c[k] for k in SHAPES), 0)

    def test_memcpy_excluded(self):
        c = self.classify('memcpy(REX_RAW_ADDR(dst),REX_RAW_ADDR(src),4);')
        self.assertEqual(sum(c[k] for k in SHAPES), 0)

    def test_direct_deref_excluded(self):
        c = self.classify('*reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)) = 1;')
        self.assertEqual(sum(c[k] for k in SHAPES), 0)

    def test_unknown_call_argument(self):
        c = self.classify('foo(REX_RAW_ADDR(ea));')
        self.assertEqual(c['passed_as_unknown_call_argument'], 1)

    def test_pointer_cast_operand(self):
        c = self.classify('auto p = reinterpret_cast<void*>(REX_RAW_ADDR(ea));')
        self.assertEqual(c['pointer_cast_operand'], 1)

    def test_assignment_rhs(self):
        c = self.classify('auto p = REX_RAW_ADDR(ea);')
        self.assertEqual(c['assignment_rhs_expression'], 1)

    def test_return_context(self):
        c = self.classify('return REX_RAW_ADDR(ea);')
        self.assertEqual(c['return_or_yield_expression'], 1)

    def test_pointer_arithmetic(self):
        c = self.classify('void* p = REX_RAW_ADDR(ea) + 4;')
        self.assertEqual(c['address_or_pointer_arithmetic'], 1)

    def test_opaque_unknown(self):
        c = self.classify('REX_RAW_ADDR(ea);')
        self.assertEqual(c['other_expression'], 1)

    def test_comments_ignored(self):
        c = self.classify('// REX_RAW_ADDR(x)\nconst char* s="REX_RAW_ADDR(foo)";')
        self.assertEqual(sum(c[k] for k in SHAPES), 0)

    def test_reconcile_and_no_leaks(self):
        code = b'private_SECRET char* p=REX_RAW_ADDR(ea); foo(REX_RAW_ADDR(a));'
        report, examples = audit([('fable_2_recomp.0.cpp', code)])
        self.assertEqual(sum(report['structural_context_counts'].values()), 2)
        self.assertEqual(report['previously_opaque_references'], 2)
        self.assertFalse(report['memexport_commit_permitted'])
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertEqual(len(examples), 0)

    def test_private_examples_opt_in(self):
        report, examples = audit([('fable_2_recomp.0.cpp', b'private_TOKEN foo(REX_RAW_ADDR(a));')], example_limit=2)
        self.assertEqual(report['previously_opaque_references'], 1)
        self.assertIn('private_TOKEN', repr(examples))
        self.assertNotIn('private_TOKEN', repr(report))

    def test_zip_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.zip'
            with ZipFile(path, 'w') as z:
                z.writestr('generated/default/fable_2_recomp.0.cpp', 'REX_RAW_ADDR(ea);')
            report, _ = audit(read_inputs(archive=path))
            self.assertEqual(report['translation_units'], 1)

    def test_duplicate_rejected(self):
        src = ('fable_2_recomp.0.cpp', b'REX_RAW_ADDR(ea)')
        with self.assertRaises(ValueError):
            audit([src, src])

    def test_cli_missing_archive_fails_closed(self):
        old = sys.argv
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output.json'
            try:
                sys.argv = ['tool', '--archive', str(Path(temp) / 'no.zip'), '--report', str(out)]
                self.assertEqual(main(), 2)
            finally:
                sys.argv = old
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
