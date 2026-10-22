#!/usr/bin/env python3
"""Collect REAL arm64 native libraries and their dependency closure for an APK.

Unlike copying four chosen .so files, resolve every non-system DT_NEEDED
library, fail on missing/incompatible deps and duplicate SONAMEs, and keep
extra dlopen-only libraries explicit. No binaries or game dumps are generated.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
from pathlib import Path
import shutil
import tempfile

if __package__:
    from .check_native_libs import REQUIRED, UNWANTED, check, parse_needed, run_readelf
else:
    # `python scripts/stage_android_libs.py` puts scripts/ on sys.path.
    from check_native_libs import REQUIRED, UNWANTED, check, parse_needed, run_readelf

ANDROID_SYSTEM_LIBRARIES = frozenset({
    'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libandroid.so',
    'libvulkan.so', 'libEGL.so', 'libGLESv1_CM.so', 'libGLESv2.so',
    'libGLESv3.so', 'libOpenSLES.so', 'libaaudio.so', 'libz.so',
    'libjnigraphics.so', 'libmediandk.so', 'libnativewindow.so',
    'libsync.so', 'libatomic.so', 'libunwind.so', 'libstdc++.so',
    'libcamera2ndk.so', 'libamidi.so', 'libbinder_ndk.so',
})


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for part in iter(lambda: fp.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def archive_inventory(paths: list[Path], search_dirs: list[Path]) -> dict[str, Path]:
    inventory: dict[str, Path] = {}
    # Select direct inputs first; only discover others from explicitly passed
    # search roots. Do not search whole workspace or the NDK (host libs!).
    for path in [*paths, *(p for folder in search_dirs for p in folder.rglob('*.so'))]:
        if not path.is_file():
            raise ValueError(f'Native input is not a file: {path}')
        if not path.name.endswith('.so'):
            raise ValueError(f'Native library filename must end in .so: {path}')
        if path.name in UNWANTED:
            raise ValueError(f'Burnout/Xerenge game library prohibited: {path.name}')
        if path.name in inventory:
            if digest(inventory[path.name]) != digest(path):
                raise ValueError(f'Conflicting native libraries named {path.name}: {inventory[path.name]} vs {path}')
        else:
            inventory[path.name] = path
    return inventory


def collect(inputs: list[Path], extras: list[Path], search_dirs: list[Path], readelf: str) -> dict[str, Path]:
    inventory = archive_inventory([*inputs, *extras], search_dirs)
    for required in REQUIRED:
        if required not in {path.name for path in inputs}:
            raise ValueError(f'Missing explicitly selected required library: {required}')
    resolved: dict[str, Path] = {}
    queue = deque([*(path.name for path in inputs), *(path.name for path in extras)])
    while queue:
        name = queue.popleft()
        if name in resolved:
            continue
        path = inventory.get(name)
        if not path:
            raise ValueError(f'Unresolved native dependency: {name}; pass --search-dir or --extra-lib')
        if name in UNWANTED:
            raise ValueError(f'Unrelated native library prohibited: {name}')
        header = run_readelf(readelf, '-h', path)
        if 'Machine:' not in header or 'AArch64' not in header:
            raise ValueError(f'Not AArch64 ELF: {name}')
        dynamic = run_readelf(readelf, '-d', path)
        resolved[name] = path
        for needed in sorted(parse_needed(dynamic)):
            if needed in UNWANTED:
                raise ValueError(f'{name} depends on unrelated Burnout library {needed}')
            if needed not in ANDROID_SYSTEM_LIBRARIES:
                if needed not in inventory:
                    raise ValueError(f'{name} requires missing {needed} (DT_NEEDED)')
                queue.append(needed)
    return resolved


def stage(inputs: list[Path], extras: list[Path], search_dirs: list[Path],
          output: Path, readelf: str) -> dict[str, Path]:
    if output.exists():
        raise ValueError(f'Output directory already exists: {output}; preserving previous results')
    for folder in search_dirs:
        if not folder.is_dir():
            raise ValueError(f'Native search directory missing: {folder}')
    chosen = collect(inputs, extras, search_dirs, readelf)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate before committing to the final destination; incomplete results
    # are discarded, so an APK cannot pick up a partial directory.
    with tempfile.TemporaryDirectory(prefix='.fable2-stage-', dir=output.parent) as tmp:
        staging = Path(tmp)
        for name, origin in chosen.items():
            shutil.copy2(origin, staging / name)
        errors = check(staging, readelf)
        if errors:
            raise ValueError('; '.join(errors))
        # TemporaryDirectory cleanup must not delete the installed files.
        # Use a second unique target and atomically rename the populated dir.
        import os
        os.rename(staging, output)
    return chosen


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game-lib', type=Path, required=True, help='Actual libfable2.so from codegen + NDK')
    p.add_argument('--gpu-lib', type=Path, required=True, help='Fable II shader-linked librexgpu-plume.so')
    p.add_argument('--runtime-lib', type=Path, required=True, help='librexruntime.so built from same SDK as GPU')
    p.add_argument('--cxx-lib', type=Path, required=True, help='Android NDK libc++_shared.so')
    p.add_argument('--extra-lib', action='append', type=Path, default=[], help='Dlopen-only extra .so (e.g. Adreno hook)')
    p.add_argument('--search-dir', action='append', type=Path, default=[], help='Search recursively for DT_NEEDED libs')
    p.add_argument('--output', type=Path, default=Path('build/android-native-stage'))
    p.add_argument('--readelf', default='llvm-readelf')
    args = p.parse_args()
    paths = [args.game_lib, args.gpu_lib, args.runtime_lib, args.cxx_lib]
    if set(path.name for path in paths) != set(REQUIRED):
        p.error('Required inputs must be libfable2.so, librexgpu-plume.so, librexruntime.so and libc++_shared.so')
    try:
        selected = stage(paths, args.extra_lib, args.search_dir, args.output, args.readelf)
    except (ValueError, OSError) as err:
        p.exit(2, f'BLOCKED: {err}\n')
    print(f'OK: staged {len(selected)} real Android libraries in {args.output}')
    for name in sorted(selected):
        print(f'  {name}  sha256={digest(selected[name])[:16]}…')
    print('NOTE: Dependency closure and exports checked, not GPU rendering or gameplay.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
