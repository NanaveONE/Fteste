import importlib.util
from pathlib import Path
import tempfile
import unittest
spec = importlib.util.spec_from_file_location('patch', Path(__file__).resolve().parents[1]/'scripts/fix_rexglue_android_float_chars.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
HEADER='''#if REX_PLATFORM_MAC
#include <locale.h>
#endif
namespace detail {
auto integer = std::from_chars(range.data(), range.data() + range.size(), result, base);
#if REX_PLATFORM_MAC
template <typename T>
inline std::from_chars_result portable_float_from_chars(const char* first, const char* last, T& value) {
  return {first, std::errc()};
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
}
'''
class Patch30(unittest.TestCase):
 def test_correct_brace_and_idempotence(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'numeric.h';f.write_text(HEADER)
   self.assertEqual(mod.patch(f),'patched')
   t=f.read_text()
   self.assertIn('value = parsed;\n  return {first + (end - buffer), std::errc()};\n}\n#endif',t)
   self.assertEqual(t.count('#if REX_PLATFORM_MAC || defined(__ANDROID__)'),2)
   self.assertEqual(mod.patch(f),'already patched')
 def test_reject_unexpected_revision(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'numeric.h';f.write_text('invalid')
   with self.assertRaises(ValueError):mod.patch(f)
if __name__=='__main__':unittest.main()
