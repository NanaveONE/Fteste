#!/usr/bin/env python3
"""Integrate host-header preflight and Ninja keep-going diagnostic mode."""
from pathlib import Path

FILE = Path('scripts/build_android_native.sh')
ANCHOR = 'python3 "$root/scripts/fix_fable2_gpu_progress_34.py" --worktree "$work"'
AUDIT = '''# Audit reachable Android host headers after worktree portability patches.
# This static check cannot replace the compiler. Its report remains private in build/.
python3 "$root/scripts/audit_android_port_36.py" --worktree "$work" \\
    --report "$root/build/android-port-audit-36.json"
'''
OLD_BUILD = 'cmake --build "$build" --target fable_2 --parallel "${BUILD_JOBS:-2}"'
NEW_BUILD = '''# Keep going after independent compile errors to collect multiple diagnostics
# in one GitHub Actions run. Ninja's -k 0 stops only when no more progress is possible.
cmake --build "$build" --target fable_2 --parallel "${BUILD_JOBS:-2}" -- -k 0'''

def apply(path=FILE):
    s = path.read_text()
    if 'audit_android_port_36.py' not in s:
        if s.count(ANCHOR) != 1:
            raise ValueError('Could not find GPU patch integration anchor')
        # The audit must run after all patches, including FrameLimiter 35.
        anchor35 = 'python3 "$root/scripts/fix_fable2_frame_limiter_35.py" --worktree "$work"'
        if s.count(anchor35) != 1:
            raise ValueError('Apply patch 35 before enabling audit 36')
        s = s.replace(anchor35, anchor35 + '\n\n' + AUDIT, 1)
    if NEW_BUILD not in s:
        if s.count(OLD_BUILD) != 1:
            raise ValueError('Expected one CMake build invocation')
        s = s.replace(OLD_BUILD, NEW_BUILD, 1)
    path.write_text(s)
    return s

if __name__ == '__main__':
    apply()
    print('OK: static Android header audit + Ninja -k 0 configured')
