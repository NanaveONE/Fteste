#!/usr/bin/env python3
"""Safely enable 16 KiB ELF page-size support in the five Fteste build/package files.

Idempotent. Validates all source anchors before modifying anything, preserving
other changes (e.g. audio, from_chars, timer, source SDK ABI patches).
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON'
TARGETS = {
    'scripts/build_rexglue_android_sdk.sh': (
        '  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 -DANDROID_STL=c++_shared \\\n',
        '  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 -DANDROID_STL=c++_shared \\\n'
        '  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \\\n',
    ),
    'scripts/build_android_native.sh': (
        '    -DANDROID_STL=c++_shared -DREXGLUE_ARM64_MARCH=armv8-a \\\n',
        '    -DANDROID_STL=c++_shared -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON -DREXGLUE_ARM64_MARCH=armv8-a \\\n',
    ),
    'scripts/build_fable_gpu.sh': (
        '  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release \\\n',
        '  -DANDROID_STL=c++_shared -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON -DCMAKE_BUILD_TYPE=Release \\\n',
    ),
    'scripts/package_android_apk.sh': (
        'python3 "$root/scripts/check_native_libs.py" "$libdir" --readelf "$readelf"\n',
        'python3 "$root/scripts/check_native_libs.py" "$libdir" --readelf "$readelf"\n'
        'python3 "$root/scripts/check_android_16k_alignment.py" --directory "$libdir"\n',
    ),
    '.github/workflows/build-android-runtime.yml': (
        '          test -s build/artifacts/rexglue-android-arm64/runtime-build-report.json\n',
        '          test -s build/artifacts/rexglue-android-arm64/runtime-build-report.json\n'
        '          python3 scripts/check_android_16k_alignment.py --directory build/artifacts/rexglue-android-arm64\n',
    ),
}


def apply(root: Path, *, check: bool = False) -> dict[str, str]:
    root = root.resolve()
    rewritten: dict[Path, str] = {}
    states: dict[str, str] = {}
    for rel, (old, new) in TARGETS.items():
        path = root / rel
        if not path.is_file():
            raise ValueError(f'Source missing: {rel}')
        current = path.read_text(encoding='utf-8')
        if current.count(new) == 1:
            states[rel] = 'verified'
        elif current.count(old) == 1 and current.count(new) == 0:
            if check:
                raise ValueError(f'16 KB build setting absent: {rel}')
            rewritten[path] = current.replace(old, new, 1)
            states[rel] = 'updated'
        else:
            raise ValueError(f'Cannot safely apply patch: unknown/multiple anchors in {rel}')
    if not (root / 'scripts/check_android_16k_alignment.py').is_file():
        raise ValueError('Missing scripts/check_android_16k_alignment.py; extract the complete ZIP first')
    # Fail closed and validate all five sources before any writes.
    for path, text in rewritten.items():
        path.write_text(text, encoding='utf-8')
    return states


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true', help='Validate that changes are already applied')
    args = parser.parse_args()
    try:
        states = apply(args.root, check=args.check)
    except (OSError, ValueError) as e:
        parser.exit(2, f'BLOCKED: {e}\n')
    for file, state in states.items():
        print(f'{state}: {file}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
