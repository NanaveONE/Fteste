import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from instrument_memexport66_guest_writes import transform, prepare, Blocked


CAS = '''ctx.cr0.eq = __sync_bool_compare_and_swap(
    reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)),
    ctx.reserved.s32, __builtin_bswap32(ctx.r11.s32));'''


class Memexport66Test(unittest.TestCase):
    def test_real_cas_sample_instrumented_once(self):
        source, counts = transform(CAS.encode())
        self.assertEqual(counts['atomic_calls_wrapped'], 1)
        self.assertEqual(counts['memory_intrinsics_wrapped'], 0)
        self.assertEqual(source.count(b'__sync_bool_compare_and_swap'), 1)
        self.assertIn(b'fable2::memexport66::Kind::Atomic', source)
        self.assertIn(b'__builtin_bswap32(ctx.r11.s32)', source)

    def test_numeric_cast_stays_unmodified(self):
        sample = b'ctx.r11.s64 = static_cast<int64_t>(ctx.r31.u64 * static_cast<uint64_t>(112));'
        rewritten, counts = transform(sample)
        self.assertEqual(rewritten, sample)
        self.assertEqual(counts['atomic_calls_wrapped'], 0)

    def test_memory_intrinsics_all_wrapped(self):
        sample = b'''memcpy(REX_RAW_ADDR(dest), src, count);
memset(REX_RAW_ADDR(dest), 0, count);
std::copy(start, end, REX_RAW_ADDR(dest));'''
        rewritten, counts = transform(sample)
        self.assertEqual(counts['memory_intrinsics_wrapped'], 3)
        self.assertEqual(rewritten.count(b'ObserveWrite'), 3)
        self.assertEqual(rewritten.count(b'memcpy'), 1)
        self.assertEqual(rewritten.count(b'memset'), 1)
        self.assertEqual(rewritten.count(b'std::copy'), 1)

    def test_non_guest_atomic_refused(self):
        with self.assertRaisesRegex(Blocked, 'Unknown atomic destination'):
            transform(b'auto x = __sync_fetch_and_add(unverified_ptr, 1);')

    def test_unbalanced_refused(self):
        with self.assertRaisesRegex(Blocked, 'Unbalanced'):
            transform(b'auto x = __sync_bool_compare_and_swap(REX_RAW_ADDR(a), 1,')

    def test_nested_atomic_refused(self):
        with self.assertRaisesRegex(Blocked, 'Nested'):
            transform(b'memset(REX_RAW_ADDR(a), __sync_fetch_and_add(REX_RAW_ADDR(b), 1), 3);')

    def test_comments_and_string_untouched(self):
        original = b'// memcpy(REX_RAW_ADDR(a), b, 1)\nchar *s="__sync_bool_compare_and_swap(x,y,z)";\n'
        result, counts = transform(original)
        self.assertEqual(result, original)
        self.assertEqual(counts['memory_intrinsics_wrapped'], 0)

    def test_duplicate_refused(self):
        result, _ = transform(CAS.encode())
        with self.assertRaisesRegex(Blocked, 'Duplicate'):
            transform(result)

    def test_macro_refused(self):
        with self.assertRaisesRegex(Blocked, 'preprocessor'):
            transform(b'#define X(x) __sync_fetch_and_add(REX_RAW_ADDR(x), 1)')

    def test_zip_provenance_and_private_stays_ignored(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            base = Path(td)
            private = base / 'guest.zip'
            with ZipFile(private, 'w') as z:
                z.writestr('generated/default/fable_2_recomp.0.cpp', CAS)
                z.writestr('generated/default/fable_2_init.cpp', '// private secret marker')
            output = ROOT / 'build' / ('m66test-' + base.name)
            report = ROOT / 'build' / ('m66report-' + base.name + '.json')
            try:
                summary = prepare(private, output, report, expect_atomics=1, expect_intrinsics=0)
                self.assertEqual(summary['translation_units'], 2)
                self.assertFalse(summary['memexport_commit_permitted'])
                self.assertNotIn('secret marker', report.read_text())
                self.assertTrue((output / 'fable_memexport_writer66.h').is_file())
                self.assertTrue((output / 'fable_2_recomp.0.cpp').is_file())
                self.assertEqual(summary['counters']['atomic_calls_wrapped'], 1)
                with self.assertRaises(Blocked):
                    prepare(private, output, report)
            finally:
                import shutil
                shutil.rmtree(output, ignore_errors=True)
                report.unlink(missing_ok=True)

    def test_wrong_count_refused_before_output(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            base = Path(td)
            private = base / 'guest.zip'
            with ZipFile(private, 'w') as z:
                z.writestr('generated/default/fable_2_recomp.0.cpp', CAS)
            output = ROOT / 'build' / ('m66bad-' + base.name)
            with self.assertRaisesRegex(Blocked, 'Atomic count drift'):
                prepare(private, output, ROOT/'build'/('bad-'+base.name+'.json'), expect_atomics=8436)
            self.assertFalse(output.exists())

    def test_compiled_observer_preserves_cas_and_memcpy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cpp = root/'smoke.cpp'
            sample = b'''#include <cstdint>
#include <cstring>
#define REX_RAW_ADDR(x) (x)
int main() {
 uint32_t value = 1;
 auto *ea = reinterpret_cast<unsigned char*>(&value);
 bool success = __sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), 1u, 4u);
 bool failure = __sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), 1u, 6u);
 unsigned char buffer[8]{};
 unsigned char src[8]{1,2,3,4,5,6,7,8};
 memcpy(REX_RAW_ADDR(buffer), src, 8);
 const auto& counters = fable2::memexport66::GetCounters();
 return !(success && !failure && value == 4 && buffer[7] == 8 &&
 counters.atomic_calls.load() == 2 && counters.intrinsic_calls.load() == 1 &&
 counters.active_calls.load() == 0 && counters.completed_calls.load() == 3);
}
'''
            result, counts = transform(sample)
            self.assertEqual(counts['atomic_calls_wrapped'], 2)
            cpp.write_bytes(result)
            (root/'fable_memexport_writer66.h').write_bytes((ROOT/'port/sdk/fable_memexport_writer66.h').read_bytes())
            for compiler in ('g++', 'clang++'):
                import shutil
                if not shutil.which(compiler):
                    continue
                exe = root / ('smoke-' + compiler)
                subprocess.run([compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                                str(cpp), '-o', str(exe)], check=True, capture_output=True, text=True)
                subprocess.run([str(exe)], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
