#!/usr/bin/env python3
"""Switch Fable GPU's isolated final overlay 52 -> 53, idempotently."""
import argparse
import runpy
from pathlib import Path

MARK='FABLE2_PLUME_53_BUILDSCRIPT'
BEFORE='''plume_overlay="$root/build/fable2-plume-overlay-52"
python3 "$root/scripts/apply_fable_plume52.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume46_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''
AFTER='''# FABLE2_PLUME_53_BUILDSCRIPT: exact overlay52 -> overlay53 layering.
plume52_overlay="$root/build/fable2-plume-overlay-52"
python3 "$root/scripts/apply_fable_plume52.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume46_overlay" --overlay "$plume52_overlay"
plume_overlay="$root/build/fable2-plume-overlay-53"
python3 "$root/scripts/apply_fable_plume53.py" \\
  --xerenge-root "$root/external/Xerenge" \\
  --base-overlay "$plume52_overlay" --overlay "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"'''

def run(root:Path,check:bool):
    path=root/'scripts/build_fable_gpu.sh'
    if not path.is_file():raise ValueError('Missing Fable GPU build script: '+str(path))
    s=path.read_text()
    if MARK in s:
        # FABLE2_PLUME_55_DOWNSTREAM_CI_53: check exact 55 then undo in RAM.
        canonical=s
        if 'FABLE2_PLUME_55_BUILDSCRIPT' in canonical:
            layer55=Path(__file__).with_name('install_fable_plume55.py')
            if not layer55.is_file():
                raise ValueError('55 marker found but installer missing')
            item55=runpy.run_path(str(layer55))
            if canonical.count(item55['MARK'])!=1 or canonical.count(item55['AFTER'])!=1 or item55['BEFORE'] in canonical:
                raise ValueError('Downstream 55 is modified or incomplete')
            canonical=canonical.replace(item55['AFTER'],item55['BEFORE'],1)
        if canonical.count(MARK)!=1 or AFTER not in canonical or BEFORE in canonical:
            raise ValueError('Existing Plume53 build integration is modified')
        print('PASS: existing Plume53 build script verified')
        return
    if check:raise ValueError('Plume53 not installed; run installer first')
    if s.count(BEFORE)!=1:
        raise ValueError(f'Expected exact Plume52 build anchor once, found {s.count(BEFORE)}')
    path.write_text(s.replace(BEFORE,AFTER,1))
    print('PASS: Plume53 overlay linked to GPU build, no Xerenge changes')

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--root',type=Path,default=Path('.'))
    a.add_argument('--check',action='store_true')
    args=a.parse_args()
    try:run(args.root,args.check)
    except (ValueError,OSError) as e:a.exit(2,f'BLOCKED: {e}\n')
if __name__=='__main__':main()
