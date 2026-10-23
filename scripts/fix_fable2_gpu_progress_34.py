#!/usr/bin/env python3
"""Declare cross-unit guest calls in the copied Fable II worktree only.

This does not provide fake definitions. The linker must resolve real guest symbols.
"""
from pathlib import Path
import argparse

REL = Path('src/core/hotfunc/unsorted/GpuProgressCheck_82B9BF90.cpp')
MARK = '// FTESTE_ANDROID_GPU_PROGRESS_DECLS_34'
ANCHOR = '#include "fable_2_funcs.284.h"'
DECLS = '''// FTESTE_ANDROID_GPU_PROGRESS_DECLS_34
// These are calls to guest code generated in other translation units.
// Deliberately declarations only: unresolved calls MUST fail at link time.
extern "C" void GetGlobalField_8221EE38(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82BA0E80(PPCContext& ctx, uint8_t* base);
'''

def patch(root: Path) -> str:
    path = root / REL
    if not path.is_file():
        raise ValueError(f'Missing worktree file: {path}')
    s = path.read_text(encoding='utf-8')
    if MARK in s:
        if s.count(MARK) != 1:
            raise ValueError('Duplicate patch marker')
        return 'already patched'
    if s.count(ANCHOR) != 1:
        raise ValueError('Unexpected original header')
    for call in ('GetGlobalField_8221EE38(ctx, base);', 'sub_82BA0E80(ctx, base);'):
        if s.count(call) != 1:
            raise ValueError(f'Unexpected guest call count: {call}')
    path.write_text(s.replace(ANCHOR, ANCHOR + '\n\n' + DECLS, 1), encoding='utf-8')
    return 'patched'

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--worktree', type=Path, required=True)
    args = ap.parse_args()
    try:
        print(patch(args.worktree))
    except (OSError, ValueError) as exc:
        ap.exit(2, f'BLOCKED: {exc}\n')
