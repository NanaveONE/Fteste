import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from classify_memexport67_raw_addresses import (
    CLASSES, classify_body, classify_sources, read_inputs, main,
)


class RawAddress67Tests(unittest.TestCase):
    def inventory(self, source):
        d = classify_body(source.encode())
        self.assertEqual(sum(d[k] for k in CLASSES), d['raw_address_references_total'])
        return d

    def test_real_cas_pattern_is_conditional_write_candidate(self):
        d = self.inventory('''ctx.cr0.eq = __sync_bool_compare_and_swap(
          reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)),
          ctx.reserved.s32, __builtin_bswap32(ctx.r11.s32));''')
        self.assertEqual(d['atomic_first_argument_write_candidate'], 1)
        self.assertEqual(d['raw_address_references_total'], 1)

    def test_numeric_casts_are_not_guest_memory_references(self):
        d = self.inventory('ctx.r11.s64 = static_cast<int64_t>(ctx.r31.u64 * static_cast<uint64_t>(112));')
        self.assertEqual(d['raw_address_references_total'], 0)

    def test_opaque_pointer_pass_does_not_infer_write(self):
        d = self.inventory('auto p = reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea));')
        self.assertEqual(d['opaque_or_other_address_usage'], 1)

    def test_direct_dereference_write(self):
        d = self.inventory('*reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)) = 123;')
        self.assertEqual(d['direct_dereference_write_candidate'], 1)

    def test_direct_dereference_read(self):
        d = self.inventory('auto v = *reinterpret_cast<const uint32_t*>(REX_RAW_ADDR(ea));')
        self.assertEqual(d['direct_dereference_read_candidate'], 1)

    def test_equality_is_not_a_write(self):
        d = self.inventory('bool ok = *reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)) == 123;')
        self.assertEqual(d['direct_dereference_read_candidate'], 1)

    def test_memcpy_destination_vs_source(self):
        d = self.inventory('memcpy(REX_RAW_ADDR(dst), REX_RAW_ADDR(src), 8);')
        self.assertEqual(d['memory_intrinsic_destination_write_candidate'], 1)
        self.assertEqual(d['memory_intrinsic_source_read_candidate'], 1)

    def test_std_copy_destination_and_fill_range(self):
        d = self.inventory('std::copy(first, last, REX_RAW_ADDR(out));\nstd::fill(REX_RAW_ADDR(begin), REX_RAW_ADDR(end), 0);')
        self.assertEqual(d['memory_intrinsic_destination_write_candidate'], 3)

    def test_comments_and_strings_ignored(self):
        d = self.inventory('// REX_RAW_ADDR(ea)\nconst char *s = "REX_RAW_ADDR(ea)";\nREX_RAW_ADDR(x);')
        self.assertEqual(d['raw_address_references_total'], 1)

    def test_nested_atomic_argument(self):
        d = self.inventory('__sync_bool_compare_and_swap(REX_RAW_ADDR(a), REX_RAW_ADDR(b), 2);')
        self.assertEqual(d['atomic_first_argument_write_candidate'], 1)
        self.assertEqual(d['atomic_other_argument_unknown'], 1)

    def test_unparsed_call_remains_uncertified(self):
        d = self.inventory('void *p = REX_RAW_ADDR(ea;')
        self.assertEqual(d['unparsed_raw_address_call'], 1)

    def test_private_report_no_sources_or_paths(self):
        body = b'private_marker memcpy(REX_RAW_ADDR(dst), REX_RAW_ADDR(src), 8);'
        report = classify_sources([('fable_2_recomp.0.cpp', body)])
        raw = json.dumps(report)
        self.assertNotIn('private_marker', raw)
        self.assertNotIn('fable_2_recomp.0.cpp', raw)
        self.assertFalse(report['memexport_commit_permitted'])
        self.assertFalse(report['global_exclusion_certified'])

    def test_empty_and_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            classify_sources([])
        sample = [('fable_2_recomp.0.cpp', b'REX_RAW_ADDR(x)')]
        with self.assertRaises(ValueError):
            classify_sources(sample + sample)

    def test_zip_archive_streamed_and_reconciled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'generated.zip'
            with ZipFile(path, 'w') as z:
                z.writestr('generated/default/fable_2_recomp.0.cpp', 'REX_RAW_ADDR(ea);')
                z.writestr('generated/default/fable_2_init.cpp', 'memset(REX_RAW_ADDR(ea), 0, 4);')
            data = classify_sources(read_inputs(archive=path))
            self.assertEqual(data['translation_units'], 2)
            self.assertEqual(data['classification_counts']['raw_address_references_total'], 2)
            self.assertEqual(data['classification_counts']['memory_intrinsic_destination_write_candidate'], 1)

    def test_cli_fails_closed_on_source_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'generated.zip'
            report = root / 'report.json'
            with ZipFile(path, 'w') as z:
                z.writestr('generated/default/fable_2_recomp.0.cpp', 'REX_RAW_ADDR(ea);')
            old = sys.argv
            try:
                sys.argv = ['program', '--archive', str(path), '--report', str(report),
                            '--expected-raw-references', '78160']
                from contextlib import redirect_stderr
                from io import StringIO
                with redirect_stderr(StringIO()):
                    result = main()
            finally:
                sys.argv = old
            self.assertEqual(result, 2)
            self.assertFalse(report.exists())


if __name__ == '__main__':
    unittest.main()
