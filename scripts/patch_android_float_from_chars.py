#!/usr/bin/env python3
"""Enable upstream ReXGlue's C-locale float parser for Android NDK libc++.

NDK 27 libc++ lacks floating-point std::from_chars overloads used by
include/rex/string/numeric.h. Upstream already contains a portable parser
for macOS based on newlocale()/strtof_l()/strtod_l(). Android API 31 provides
those libc functions too. Extend its FOUR #if guards to Android without
changing any other platform, parser behavior, or versioned upstream source.

Only modifies a disposable ReXGlue SDK clone under Fteste/build/.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import re
import stat
import tempfile

RELATIVE_HEADER = Path('include/rex/string/numeric.h')
ORIGINAL = '#if REX_PLATFORM_MAC'
PATCHED = '#if REX_PLATFORM_MAC || defined(__ANDROID__)'
EXPECTED_GUARDS = 4
EXPECTED_ANCHORS = (
    '#include <locale.h>',
    'portable_float_from_chars',
    'newlocale(LC_NUMERIC_MASK, "C", nullptr)',
    'strtof_l(buffer, &end, c_numeric_locale)',
    'strtod_l(buffer, &end, c_numeric_locale)',
    'std::from_chars(range.data(), range.data() + range.size(), result,',
    'std::from_chars(p, end, v.f32[i], std::chars_format::general)',
)


def _count_guards(source: str, guard: str) -> int:
    return sum(line == guard for line in source.splitlines())


def patch_source(source: str) -> tuple[str, bool]:
    for anchor in EXPECTED_ANCHORS:
        if anchor not in source:
            raise ValueError(f'ReXGlue numeric.h changed; missing anchor: {anchor}')
    originals = _count_guards(source, ORIGINAL)
    already = _count_guards(source, PATCHED)
    if originals == 0 and already == EXPECTED_GUARDS:
        return source, False
    if originals != EXPECTED_GUARDS or already != 0:
        raise ValueError(
            f'Upstream numeric.h layout changed/partially patched: '
            f'{originals} original and {already} Android guards; expected '
            f'{EXPECTED_GUARDS} original or patched')
    changed = re.sub(r'^#if REX_PLATFORM_MAC$', PATCHED, source, flags=re.MULTILINE)
    if _count_guards(changed, PATCHED) != EXPECTED_GUARDS or _count_guards(changed, ORIGINAL) != 0:
        raise ValueError('Unexpected preprocessor guards after patch')
    return changed, True


def patch_clone(sdk: Path, root: Path, *, check_only: bool = False) -> bool:
    root = root.expanduser().resolve()
    sdk = sdk.expanduser().resolve()
    if not sdk.is_relative_to(root / 'build'):
        raise ValueError('Refusing to modify SDK outside disposable Fteste/build/ clone')
    if not (sdk / 'CMakeLists.txt').is_file():
        raise ValueError('ReXGlue SDK source clone missing CMakeLists.txt')
    header = sdk / RELATIVE_HEADER
    if not header.is_file() or header.is_symlink():
        raise ValueError(f'Missing/nonregular ReXGlue numeric header: {header}')
    source = header.read_text(encoding='utf-8')
    changed, needed = patch_source(source)
    if check_only:
        if needed:
            raise ValueError('Android floating-point parser patch has not been applied')
        return False
    if not needed:
        return False
    fd, temp = tempfile.mkstemp(prefix='.numeric-android-', suffix='.h', dir=header.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as writer:
            writer.write(changed)
        os.chmod(temp, stat.S_IMODE(header.stat().st_mode))
        os.replace(temp, header)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true', help='Fail if source lacks the patch')
    args = parser.parse_args()
    try:
        modified = patch_clone(args.sdk, args.root, check_only=args.check)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f'BLOCKED: {exc}\n')
    print('OK: Android numeric C-locale parser ' + ('patched in private SDK' if modified else 'already patched'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
