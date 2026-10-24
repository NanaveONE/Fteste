import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from classify_memexport68_opaque_helpers import classify, opaque_hints


class OpaqueHelpers68(unittest.TestCase):
    def test_read_helper_hint(self):
        self.assertEqual(opaque_hints(b'auto x = PPC_LOAD32(REX_RAW_ADDR(ea));')['helper_read_name'], 1)

    def test_write_helper_hint(self):
        self.assertEqual(opaque_hints(b'PPC_STORE32(REX_RAW_ADDR(ea), value);')['helper_write_name'], 1)

    def test_generic_helper_remains_hint(self):
        self.assertEqual(opaque_hints(b'REX_FOO(REX_RAW_ADDR(ea));')['helper_other_name'], 1)

    def test_address_value_expression(self):
        self.assertEqual(opaque_hints(b'auto guest = REX_RAW_ADDR(ea);')['address_value_expression'], 1)

    def test_unknown_expression(self):
        self.assertEqual(opaque_hints(b'const auto x = REX_RAW_ADDR(ea) + 2;')['address_value_expression'], 1)

    def test_cas_is_already_classified_and_excluded(self):
        s=b'ctx.cr0.eq = __sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), old, value);'
        self.assertEqual(sum(opaque_hints(s).values()), 0)

    def test_memcpy_is_already_classified_and_excluded(self):
        self.assertEqual(sum(opaque_hints(b'memcpy(REX_RAW_ADDR(dst), REX_RAW_ADDR(src), 4);').values()), 0)

    def test_comments_and_strings_not_counted(self):
        self.assertEqual(sum(opaque_hints(b'// REX_RAW_ADDR(x)\nconst char *x="REX_RAW_ADDR(y)";').values()),0)

    def test_provenance_and_no_source_leak(self):
        report=classify([('fable_2_recomp.0.cpp', b'private_marker PPC_STORE32(REX_RAW_ADDR(ea), value);')])
        self.assertEqual(report['previously_classified_as_opaque'], 1)
        self.assertEqual(report['opaque_context_hints']['helper_write_name'], 1)
        self.assertFalse(report['memexport_commit_permitted'])
        self.assertNotIn('private_marker', json.dumps(report))

    def test_empty_input_fails_closed(self):
        with self.assertRaises(ValueError):classify([])

    def test_zip_input_supported(self):
        from classify_memexport67_raw_addresses import read_inputs
        with tempfile.TemporaryDirectory() as tmp:
            z=Path(tmp)/'input.zip'
            with ZipFile(z,'w') as f:
                f.writestr('generated/default/fable_2_recomp.0.cpp','PPC_LOAD32(REX_RAW_ADDR(ea));')
            self.assertEqual(classify(read_inputs(archive=z))['previously_classified_as_opaque'],1)


if __name__=='__main__': unittest.main()
