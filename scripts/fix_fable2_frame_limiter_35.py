#!/usr/bin/env python3
"""Port the Windows-only host pause in Fable II frame limiter to Android."""
import argparse
from pathlib import Path

REL = Path('src/core/hotfunc/vblank/FrameLimiterWait_82242628.cpp')
OLD_INCLUDE = '#include <windows.h>'
NEW_INCLUDE = '#if defined(_WIN32)\n#include <windows.h>\n#else\n#include <chrono>\n#include <thread>\n#endif  // _WIN32 // FABLE2_FRAME_LIMITER_ANDROID_35'
OLD_CALL = '  WaitForSingleObjectEx(nullptr, hundredNs > 0 ? hundredNs : 1, TRUE);'
NEW_CALL = '''#if defined(_WIN32)
  WaitForSingleObjectEx(nullptr, hundredNs > 0 ? hundredNs : 1, TRUE);
#else
  // A portable host-only pause. No PPC guest state is modified.
  std::this_thread::sleep_for(std::chrono::nanoseconds(kPauseNs));
#endif'''

def patch(root):
    path = root / REL
    src = path.read_text(encoding='utf-8')
    if 'FABLE2_FRAME_LIMITER_ANDROID_35' in src:
        if NEW_CALL not in src:
            raise ValueError('Partial patch 35 detected')
        return 'already patched'
    for old in (OLD_INCLUDE, OLD_CALL):
        if src.count(old) != 1:
            raise ValueError(f'Unexpected upstream revision: {old!r} occurs {src.count(old)} times')
    result = src.replace(OLD_INCLUDE, NEW_INCLUDE, 1).replace(OLD_CALL, NEW_CALL, 1)
    path.write_text(result, encoding='utf-8')
    return 'patched'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worktree', type=Path, required=True)
    args = parser.parse_args()
    print(patch(args.worktree))
