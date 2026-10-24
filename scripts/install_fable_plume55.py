#!/usr/bin/env python3
"""Layer overlay55 after 53 without modifying the Xerenge source tree."""
import argparse
import runpy
from pathlib import Path

MARK='FABLE2_PLUME_55_BUILDSCRIPT'
BEFORE='''plume_overlay="$root/build/fable2-plume-overlay-53"
python3 "$root/scripts/apply_fable_plume53.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume52_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''
AFTER='''# FABLE2_PLUME_55_BUILDSCRIPT: keep immutable overlay53 for verified input.
plume53_overlay="$root/build/fable2-plume-overlay-53"
python3 "$root/scripts/apply_fable_plume53.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume52_overlay" --overlay "$plume53_overlay"
plume_overlay="$root/build/fable2-plume-overlay-55"
python3 "$root/scripts/apply_fable_plume55.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume53_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''

def run(root:Path,check:bool):
    path=root/'scripts/build_fable_gpu.sh'
    if not path.is_file(): raise ValueError('Fable GPU build script missing')
    contents=path.read_text()
    if MARK in contents:
        downstream=runpy.run_path(str(Path(__file__).with_name('normalize_fable_plume_build.py')))
        canonical=downstream['canonical_stage55'](contents)
        if canonical.count(MARK)!=1 or canonical.count(AFTER)!=1 or BEFORE in canonical:
            raise ValueError('Installed overlay55 script modified')
        print('PASS: Plume55 script already installed, verified')
        return
    if check: raise ValueError('Plume55 not installed')
    if contents.count(BEFORE)!=1: raise ValueError('Missing exact overlay53 build anchor')
    path.write_text(contents.replace(BEFORE,AFTER,1))
    print('PASS: GPU builder layered Plume53 -> Plume55')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    try:run(a.root,a.check)
    except (ValueError,OSError) as e:p.exit(2,f'BLOCKED: {e}\n')
