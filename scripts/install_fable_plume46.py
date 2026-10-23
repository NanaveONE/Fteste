#!/usr/bin/env python3
"""Integrate Plume46 isolated overlay without touching Xerenge submodules.

Run only once after ZIP extraction; all exact anchor checks are evaluated
before writing either Fteste build file (fail closed).
"""
import argparse
from pathlib import Path

MARK = 'FABLE2_PLUME_46_BUILDSCRIPT'


def one(src, old, new, name):
    count = src.count(old)
    if count != 1:
        raise ValueError(f'{name}: expected one exact anchor, got {count}')
    return src.replace(old, new, 1)


def patch_shell(s):
    old = '''plume_overlay="$root/build/fable2-plume-overlay-v2"
python3 "$root/scripts/prepare_fable_plume.py" \\
  --xerenge-root "$root/external/Xerenge" --output "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''
    new = '''# FABLE2_PLUME_46_BUILDSCRIPT: keep the old verified overlay immutable.
base_plume_overlay="$root/build/fable2-plume-overlay-v2"
python3 "$root/scripts/prepare_fable_plume.py" \\
  --xerenge-root "$root/external/Xerenge" --output "$base_plume_overlay"
plume_overlay="$root/build/fable2-plume-overlay-46"
python3 "$root/scripts/apply_fable_plume46.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$base_plume_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''
    s = one(s, old, new, 'overlay script')
    s = one(s, '  -DFABLE2_PLUME_DRAW_CPP="$plume_overlay/plume_draw.cpp" \\\n',
            '  -DFABLE2_PLUME_OVERLAY_DIR="$plume_overlay" \\\n'
            '  -DFABLE2_PLUME_DRAW_CPP="$plume_overlay/plume_draw.cpp" \\\n',
            'CMake include overlay')
    return s


def patch_cmake(s):
    anchor='target_compile_definitions(rexgpu-plume PRIVATE XERENGE_HAS_SHADER_CACHE=1 FABLE2_PLUME_PORT=1)'
    new = '''# FABLE2_PLUME_46_BUILDSCRIPT: override only plume_draw.h for the Fable build.
# Its GuestDrawSnapshot layout MUST be consistent in all Plume translation units.
if(NOT DEFINED FABLE2_PLUME_OVERLAY_DIR OR
   NOT EXISTS "${FABLE2_PLUME_OVERLAY_DIR}/plume_renderer/plume_draw.h")
  message(FATAL_ERROR "Fable Plume46 patched snapshot header missing")
endif()
target_include_directories(rexgpu-plume BEFORE PRIVATE
  "${FABLE2_PLUME_OVERLAY_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}")
''' + anchor
    return one(s,anchor,new,'Plume build include directory')


def run(root: Path):
    path1 = root/'scripts/build_fable_gpu.sh'
    path2 = root/'port/gpu/CMakeLists.txt'
    originals = {path1: patch_shell, path2: patch_cmake}
    changes = {}
    for path, fn in originals.items():
        if not path.is_file(): raise ValueError(f'{path} is missing')
        old=path.read_text()
        if MARK in old:
            raise ValueError('Already installed 46: refusing a second rewrite')
        changes[path]=fn(old)
    for path, new in changes.items():path.write_text(new)
    print('PASS: GPU build integrated with separate, reproducible Plume46 overlay')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('.'))
    args=parser.parse_args()
    try:run(args.root)
    except (ValueError,OSError) as exc:parser.exit(2,f'BLOCKED: {exc}\n')

if __name__=='__main__':main()
