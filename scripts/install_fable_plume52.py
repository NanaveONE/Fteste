#!/usr/bin/env python3
"""Wire Plume52 overlay into the existing Fable2 GPU builder, once only.

Idempotent verification is handled by --check (for GitHub Actions).
"""
import argparse
import runpy
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
        # CI-54: when overlay53 extends overlay52, verify the *entire exact*
        # extension first, then temporarily undo it in RAM to verify 52.
        # Never rewrite the installed build script or relax the 52 anchors.
        canonical=s
        if 'FABLE2_PLUME_53_BUILDSCRIPT' in s:
            next_layer=Path(__file__).with_name('install_fable_plume53.py')
            if not next_layer.is_file():
                raise ValueError('Plume53 marker present but 53 installer is missing')
            layer53=runpy.run_path(str(next_layer))
            mark53=layer53['MARK']
            old53=layer53['BEFORE']
            new53=layer53['AFTER']
            if s.count(mark53)!=1 or s.count(new53)!=1 or old53 in s:
                raise ValueError('Plume53 integration has changed or is incomplete')
            canonical=s.replace(new53,old53,1)
        if canonical.count(AFTER)!=1 or BEFORE in canonical or canonical.count(MARK)!=1:
            raise ValueError('Plume52 installed, but script differs from expected content')
        print('PASS: Plume52 installed and verified (including downstream 53 if present)')
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
