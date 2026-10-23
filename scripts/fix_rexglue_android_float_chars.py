#!/usr/bin/env python3
"""Patch the pinned ReXGlue SDK float parser for Android NDK libc++.

Modifies only ignored build/deps checkout, never the tracked submodule.
"""
import argparse
from pathlib import Path
import sys


def patch(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Missing SDK header: {path}")
    text = path.read_text()
    marker = '#if REX_PLATFORM_MAC || defined(__ANDROID__)'
    if marker in text:
        return 'already patched'
    if text.count('#if REX_PLATFORM_MAC') != 4:
        raise ValueError('Unexpected ReXGlue numeric.h revision: refusing patch')
    if text.count('std::from_chars(range.data(), range.data() + range.size(), result,') != 2:
        raise ValueError('Expected integer and float parser call sites not found')
    if text.count('std::from_chars(p, end, v.f32[i], std::chars_format::general)') != 1:
        raise ValueError('Expected vec128 float parser not found')
    # Android's libc++ lacks floating-point std::from_chars in NDK r27c.
    # Retain the upstream macOS C-locale implementation; Android uses the
    # bionic strtof/strtod parser with a bounded input copy and pointer checks.
    text = text.replace('#if REX_PLATFORM_MAC\n#include <locale.h>', '#if REX_PLATFORM_MAC\n#include <locale.h>')
    start = text.index('#if REX_PLATFORM_MAC\ntemplate <typename T>')
    end = text.index('\n#endif', start) + len('\n#endif')
    block = text[start:end]
    assert 'portable_float_from_chars' in block
    addition = '''
#elif defined(__ANDROID__)
template <typename T>
inline std::from_chars_result portable_float_from_chars(const char* first, const char* last,
                                                        T& value) {
  static_assert(std::is_same_v<T, float> || std::is_same_v<T, double>);
  if (first == last || *first == '+' || *first == ' ' || *first == '\\t' ||
      *first == '\\n' || *first == '\\r') {
    return {first, std::errc::invalid_argument};
  }
  const size_t len = static_cast<size_t>(last - first);
  char buffer[128];
  if (len >= sizeof(buffer)) {
    return {first, std::errc::result_out_of_range};
  }
  std::memcpy(buffer, first, len);
  buffer[len] = '\\0';
  char* end = nullptr;
  errno = 0;
  T parsed;
  if constexpr (std::is_same_v<T, float>) {
    parsed = std::strtof(buffer, &end);
  } else {
    parsed = std::strtod(buffer, &end);
  }
  if (end == buffer) return {first, std::errc::invalid_argument};
  if (errno == ERANGE) return {first + (end - buffer), std::errc::result_out_of_range};
  value = parsed;
  return {first + (end - buffer), std::errc()};
}
'''
    text = text[:start] + block[:-len('\n#endif')] + addition + '#endif' + text[end:]
    # Only two call sites; the mac-only include and portable implementation stay untouched.
    text = text.replace('#if REX_PLATFORM_MAC\n    auto [p, error] = portable_float_from_chars', marker + '\n    auto [p, error] = portable_float_from_chars')
    text = text.replace('#if REX_PLATFORM_MAC\n      auto result = detail::portable_float_from_chars', marker + '\n      auto result = detail::portable_float_from_chars')
    if 'value = parsed;\n  return {first + (end - buffer), std::errc()};\n}\n#endif' not in text:
        raise ValueError('Android parser missing closing brace')
    if text.count(marker) != 2:
        raise ValueError('Unexpected float parser call sites')
    path.write_text(text)
    return 'patched'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sdk', type=Path, required=True)
    args = p.parse_args()
    try:
        print(patch(args.sdk / 'include/rex/string/numeric.h'))
    except ValueError as exc:
        print(f'BLOCKED: {exc}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
