"""Regression tests for Android NDK 27 missing floating std::from_chars.

Do not require an NDK for normal CI; a host C++ smoke verifies the actual
C-locale fallback implementation. Android ARM64 compilation remains separate.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.patch_android_float_from_chars import patch_source, patch_clone, PATCHED

ROOT = Path(__file__).resolve().parents[1]

UPSTREAM_LAYOUT = '''#pragma once
#if REX_PLATFORM_MAC
#include <locale.h>
#endif
#if REX_PLATFORM_MAC
// portable function
inline void portable_float_from_chars() {
 newlocale(LC_NUMERIC_MASK, "C", nullptr);
 strtof_l(buffer, &end, c_numeric_locale);
 strtod_l(buffer, &end, c_numeric_locale);
}
#endif
#if REX_PLATFORM_MAC
 auto [p, error] = portable_float_from_chars(range.data(), range.data() + range.size(), result);
#else
 auto [p, error] = std::from_chars(range.data(), range.data() + range.size(), result,
                                  std::chars_format::general);
#endif
#if REX_PLATFORM_MAC
 auto result = detail::portable_float_from_chars(p, end, v.f32[i]);
#else
 auto result = std::from_chars(p, end, v.f32[i], std::chars_format::general);
#endif
'''


class FloatCharconvAndroidTests(unittest.TestCase):
    def test_exact_four_guards_and_idempotency(self):
        patched, did_modify = patch_source(UPSTREAM_LAYOUT)
        self.assertTrue(did_modify)
        self.assertEqual(patched.splitlines().count(PATCHED), 4)
        self.assertEqual(patched.splitlines().count('#if REX_PLATFORM_MAC'), 0)
        self.assertIn('strtof_l(buffer, &end, c_numeric_locale)', patched)
        self.assertIn('std::from_chars(p, end, v.f32[i]', patched)
        self.assertEqual(patch_source(patched), (patched, False))

    def test_fail_closed_on_upstream_changes_or_partial_application(self):
        with self.assertRaisesRegex(ValueError, 'layout changed'):
            patch_source(UPSTREAM_LAYOUT.replace('#if REX_PLATFORM_MAC\n', '', 1))
        partially = UPSTREAM_LAYOUT.replace('#if REX_PLATFORM_MAC', PATCHED, 1)
        with self.assertRaisesRegex(ValueError, 'partially patched'):
            patch_source(partially)
        with self.assertRaisesRegex(ValueError, 'missing anchor'):
            patch_source(UPSTREAM_LAYOUT.replace('strtod_l(buffer, &end, c_numeric_locale)', ''))

    def test_never_modifies_original_sdk_or_submodule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = root / 'build/deps/rexglue-xerenge'
            file = sdk / 'include/rex/string/numeric.h'
            file.parent.mkdir(parents=True)
            (sdk / 'CMakeLists.txt').write_text('')
            file.write_text(UPSTREAM_LAYOUT)
            with self.assertRaisesRegex(ValueError, 'not been applied'):
                patch_clone(sdk, root, check_only=True)
            self.assertTrue(patch_clone(sdk, root))
            self.assertFalse(patch_clone(sdk, root))
            self.assertFalse(patch_clone(sdk, root, check_only=True))
            self.assertEqual(file.read_text().splitlines().count(PATCHED), 4)
            with self.assertRaisesRegex(ValueError, 'outside disposable'):
                patch_clone(root / 'external/rexglue-xerenge', root)

    def test_real_c_locale_fallback_compiles_and_parses(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('Host C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            cpp = Path(tmp) / 'test.cpp'
            cpp.write_text(r'''
#define _GNU_SOURCE 1
#include <cassert>
#include <charconv>
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <locale.h>
#include <type_traits>
// Matching the upstream ReXGlue function, enabled for Android.
template <typename T>
inline std::from_chars_result portable_float_from_chars(const char* first, const char* last,
                                                        T& value) {
  static_assert(std::is_same_v<T, float> || std::is_same_v<T, double>);
  if (first == last || *first == '+' || *first == ' ' || *first == '\f' || *first == '\n' ||
      *first == '\r' || *first == '\t' || *first == '\v') {
    return {first, std::errc::invalid_argument};
  }
  const size_t len = static_cast<size_t>(last - first);
  char buffer[128];
  if (len >= sizeof(buffer)) return {first, std::errc::result_out_of_range};
  std::memcpy(buffer, first, len);
  buffer[len] = '\0';
  static locale_t c_numeric_locale = newlocale(LC_NUMERIC_MASK, "C", nullptr);
  if (!c_numeric_locale) return {first, std::errc::invalid_argument};
  char* end = nullptr;
  errno = 0;
  T parsed_value;
  if constexpr (std::is_same_v<T, float>) parsed_value = strtof_l(buffer, &end, c_numeric_locale);
  else parsed_value = strtod_l(buffer, &end, c_numeric_locale);
  if (end == buffer) return {first, std::errc::invalid_argument};
  if (errno == ERANGE) return {first + (end-buffer), std::errc::result_out_of_range};
  value = parsed_value;
  return {first + (end-buffer), std::errc()};
}
int main() {
    double d = 0;
    const char *txt = "123.75tail";
    auto ok = portable_float_from_chars(txt, txt+10, d);
    assert(ok.ec == std::errc() && ok.ptr == txt+6 && d == 123.75);
    float f = 0;
    txt = "-0.25";
    ok = portable_float_from_chars(txt, txt+5, f);
    assert(ok.ec == std::errc() && f == -0.25f);
    txt = "+1.2";
    ok = portable_float_from_chars(txt, txt+4, f);
    assert(ok.ec == std::errc::invalid_argument);
    txt = " 1.2";
    ok = portable_float_from_chars(txt, txt+4, f);
    assert(ok.ec == std::errc::invalid_argument);
    txt = "1e999";
    ok = portable_float_from_chars(txt, txt+5, d);
    assert(ok.ec == std::errc::result_out_of_range);
}
''')
            exe = Path(tmp) / 'test'
            result = subprocess.run([compiler, '-std=c++20', '-O0', str(cpp), '-o', str(exe)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_android_script_patches_before_configuring_cmake(self):
        script = (ROOT / 'scripts/build_rexglue_android_sdk.sh').read_text()
        self.assertIn('patch_android_float_from_chars.py', script)
        self.assertLess(script.index('patch_android_float_from_chars.py'), script.index('cmake -S "$sdk"'))


if __name__ == '__main__':
    unittest.main()
