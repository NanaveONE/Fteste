import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from classify_memexport65_guest_access import classify, classify_body, mask_non_code


class MemExport65Tests(unittest.TestCase):
    def test_user_real_numeric_samples_are_not_memory_writes(self):
        sample = b'''// mulli r11,r31,112
ctx.r11.s64 = static_cast<int64_t>(ctx.r31.u64 * static_cast<uint64_t>(112));
ctx.r27.s64 = static_cast<int64_t>(ctx.r28.u64 * static_cast<uint64_t>(21));
ctx.r10.s64 = static_cast<int64_t>(ctx.r31.u64 * static_cast<uint64_t>(60));'''
        c = classify_body(sample)
        self.assertEqual(c['numeric_static_casts'], 6)
        self.assertEqual(c.get('pointer_casts', 0), 0)
        self.assertEqual(c.get('atomic_potential_write_calls', 0), 0)
        self.assertEqual(c.get('direct_guest_write_candidates', 0), 0)

    def test_user_real_atomic_compare_and_swap(self):
        sample = b'''ctx.cr0.eq = __sync_bool_compare_and_swap(
    reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)),
    ctx.reserved.s32, __builtin_bswap32(ctx.r11.s32));'''
        c = classify_body(sample)
        self.assertEqual(c['pointer_casts_with_rex_raw_addr'], 1)
        self.assertEqual(c['atomic_potential_write_calls'], 1)
        self.assertEqual(c['atomic_conditional_write_candidates'], 1)
        self.assertEqual(c['atomic_guest_memory_write_candidates'], 1)
        self.assertEqual(c.get('direct_dereference_write_candidates', 0), 0)

    def test_direct_guest_store(self):
        c = classify_body(b'*reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)) = val;')
        self.assertEqual(c['direct_guest_write_candidates'], 1)

    def test_no_false_store_inside_cast_argument(self):
        c = classify_body(b'auto ptr = reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea = bb));')
        self.assertEqual(c.get('direct_guest_write_candidates', 0), 0)

    def test_memory_intrinsic_destinations(self):
        c = classify_body(b'''memcpy(REX_RAW_ADDR(dest), src, len);
memset(REX_RAW_ADDR(dest), 0, len);
memmove(local, REX_RAW_ADDR(src), len);
std::copy(start, end, REX_RAW_ADDR(dest));''')
        self.assertEqual(c['memory_intrinsic_calls'], 4)
        self.assertEqual(c['memory_intrinsic_guest_destination_candidates'], 3)

    def test_comments_strings_and_atomic_load(self):
        src = b'''// __sync_bool_compare_and_swap(REX_RAW_ADDR(x), a, b)
char* s = "REX_RAW_ADDR(x)";
/* memcpy(REX_RAW_ADDR(dest), src, size); */
__atomic_load_n(REX_RAW_ADDR(addr), 0);
__atomic_thread_fence(0);'''
        c = classify_body(src)
        self.assertEqual(c.get('atomic_potential_write_calls', 0), 0)
        self.assertEqual(c['atomic_load_calls'], 1)
        self.assertEqual(c['atomic_fence_calls'], 1)
        self.assertEqual(c.get('memory_intrinsic_calls', 0), 0)
        self.assertEqual(c['rex_raw_addr_calls'], 1)

    def test_opaque_unknown_atomic_kept_candidate(self):
        c = classify_body(b'__sync_fetch_and_add(x, 1);')
        self.assertEqual(c['atomic_address_unknown_write_candidates'], 1)

    def test_unparsed_syntax_is_reported(self):
        c = classify_body(b'reinterpret_cast<uint32_t*(oops; __atomic_exchange_n(')
        self.assertGreater(c.get('unparsed_cast_syntax', 0), 0)

    def test_provenance_and_no_private_source_leakage(self):
        private = b'''// SECRET_PRIVATE_GAME_MARKER
*reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)) = 2;'''
        report = classify([('fable_2_recomp.0.cpp', private)])
        self.assertEqual(report['translation_units'], 1)
        self.assertEqual(report['classification_counts']['direct_guest_write_candidates'], 1)
        self.assertFalse(report['memexport_commit_permitted'])
        self.assertFalse(report['global_exclusion_certified'])
        self.assertNotIn('SECRET_PRIVATE_GAME_MARKER', json.dumps(report))
        self.assertNotIn('fable_2_recomp.0.cpp', json.dumps(report))

    def test_zero_hits_not_certified(self):
        r = classify([('fable_2_init.cpp', b'int x = 1;')])
        self.assertEqual(r['classification_counts']['atomic_calls_all'], 0)
        self.assertFalse(r['direct_guest_stores_fully_instrumented'])

    def test_private_zip_reader_supports_generated_prefix(self):
        from audit_memexport63_guest_writes import read_sources
        with tempfile.TemporaryDirectory() as d:
            zip_path = Path(d) / 'private.zip'
            with ZipFile(zip_path, 'w', ZIP_DEFLATED) as z:
                z.writestr('generated/default/fable_2_recomp.15.cpp',
                           '*reinterpret_cast<int*>(REX_RAW_ADDR(ea)) = 1;')
                z.writestr('generated/default/sources.cmake', 'no source here')
            report = classify(read_sources(archive=zip_path))
            self.assertEqual(report['translation_units'], 1)
            self.assertEqual(report['classification_counts']['direct_guest_write_candidates'], 1)

    def test_empty_fails(self):
        with self.assertRaises(ValueError):
            classify([])


if __name__ == '__main__':
    unittest.main()
