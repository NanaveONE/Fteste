#!/usr/bin/env python3
"""Install a strictly opt-in 583/588 probe into the existing GPU builder.

Do not change the existing 46..55 overlay chain. No private data is used in
this installer. An ordinary build remains all-or-nothing (588/588).
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARK='FABLE2_GPU_PROBE56_OPT_IN'
BS = chr(92)  # shell continuation; avoid accidental Python line escaping
ALIGN_BEFORE = "\n".join([
    "  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release " + BS,
    "  '-DCMAKE_C_FLAGS=-march=armv8-a -moutline-atomics' " + BS,
    "  '-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics' " + BS,
])
ALIGN_AFTER = "\n".join([
    "  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release " + BS,
    "  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON " + BS,
    "  '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384' " + BS,
    "  '-DCMAKE_C_FLAGS=-march=armv8-a -moutline-atomics' " + BS,
    "  '-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics' " + BS,
])

BEFORE='''python3 "$root/scripts/validate_xenosrecomp_cache.py" \\
  --cache "$shader_cache" --scan-dir "$shader_dir/xenos-scan" \\
  --min-coverage 1.0 --report "$shader_dir/spirv-coverage-report.json"'''
AFTER='''# FABLE2_GPU_PROBE56_OPT_IN: diagnostic compilation only, never an APK.
# Without explicit opt-in the full 588/588 production gate is unchanged.
if [[ "${FABLE2_GPU_PROBE56:-0}" == "1" ]]; then
  : "${FABLE2_GPU_DIAGNOSTIC43_ZIP:?Set PRIVATE diagnostic43 ZIP for Fable II probe56}"
  python3 "$root/scripts/validate_gpu_probe56.py" \\
    --cache "$shader_cache" --scan-dir "$shader_dir/xenos-scan" \\
    --shader-report "$shader_report" --diagnostic "$FABLE2_GPU_DIAGNOSTIC43_ZIP" \\
    --report "$shader_dir/gpu-probe56-report.json"
else
  python3 "$root/scripts/validate_xenosrecomp_cache.py" \\
    --cache "$shader_cache" --scan-dir "$shader_dir/xenos-scan" \\
    --min-coverage 1.0 --report "$shader_dir/spirv-coverage-report.json"
fi'''


def run(root:Path, check:bool) -> None:
    f=root/'scripts/build_fable_gpu.sh'
    if not f.is_file(): raise ValueError('Missing existing Fable GPU build script')
    s=f.read_text()
    if MARK in s:
        if (s.count(MARK)!=1 or s.count(AFTER)!=1 or BEFORE in s or
            s.count(ALIGN_AFTER)!=1 or ALIGN_BEFORE in s):
            raise ValueError('Probe56 or 16KiB linker settings modified')
        print('PASS: GPU probe56 is installed, production validation unchanged')
        return
    if check:raise ValueError('Probe56 not installed')
    if s.count(BEFORE)!=1:raise ValueError('Expected exactly one pinned shader coverage gate')
    if s.count(ALIGN_BEFORE)!=1:raise ValueError('Expected exactly one original ARM64 CMake anchor')
    if 'FABLE2_PLUME_55_BUILDSCRIPT' not in s:
        raise ValueError('Apply Plume55 and verify overlay55 first')
    # Both modifications happen in memory before a single file write.
    f.write_text(s.replace(BEFORE,AFTER,1).replace(ALIGN_BEFORE,ALIGN_AFTER,1))
    print('PASS: opt-in GPU compilation probe56 installed; production requires 588/588')


if __name__ == '__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--root',type=Path,default=Path('.'))
    a.add_argument('--check',action='store_true')
    x=a.parse_args()
    try:run(x.root,x.check)
    except (OSError,ValueError) as exc:a.exit(2,f'BLOCKED: {exc}\n')
