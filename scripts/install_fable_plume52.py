#!/usr/bin/env python3
"""Wire Plume52 overlay into the existing Fable2 GPU builder, once only.

Idempotent verification is handled by --check (for GitHub Actions).
"""
import argparse
from pathlib import Path

MARK='FABLE2_PLUME_52_BUILDSCRIPT'
BEFORE='''plume_overlay="$root/build/fable2-plume-overlay-46"
python3 "$root/scripts/apply_fable_plume46.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$base_plume_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''
AFTER='''# FABLE2_PLUME_52_BUILDSCRIPT: layered over unchanged verified 46.
plume46_overlay="$root/build/fable2-plume-overlay-46"
python3 "$root/scripts/apply_fable_plume46.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$base_plume_overlay" --overlay "$plume46_overlay"
plume_overlay="$root/build/fable2-plume-overlay-52"
python3 "$root/scripts/apply_fable_plume52.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume46_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''

def run(root:Path,check:bool):
    path=root/'scripts/build_fable_gpu.sh'
    if not path.is_file():raise ValueError(f'Cannot find GPU build script: {path}')
    s=path.read_text()
    if MARK in s:
        if AFTER not in s or BEFORE in s or s.count(MARK)!=1:
            raise ValueError('Plume52 installed, but script differs from expected content')
        print('PASS: Plume52 already installed and verified')
        return
    if check:
        raise ValueError('Plume52 not installed (run without --check first)')
    if s.count(BEFORE)!=1:raise ValueError(f'Expected exactly one Plume46 build anchor, found {s.count(BEFORE)}')
    path.write_text(s.replace(BEFORE,AFTER,1))
    print('PASS: Plume52 build invocation installed')

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--root',type=Path,default=Path('.'))
    a.add_argument('--check',action='store_true')
    x=a.parse_args()
    try: run(x.root,x.check)
    except (ValueError,OSError) as e:a.exit(2,f'BLOCKED: {e}\n')
