#!/usr/bin/env python3
"""Install worktree-only diagnostics portability hook in build_android_native.sh."""
from pathlib import Path

p = Path('scripts/build_android_native.sh')
s = p.read_text(encoding='utf-8')
cmd = 'python3 "$root/scripts/fix_fable2_android_diagnostics_33.py" --worktree "$work"'
if cmd not in s:
    anchor = '# Codegen and Fable\'s Lua staging operate on the *worktree*, never on the'
    if s.count(anchor) != 1:
        raise SystemExit('BLOCKED: worktree preparation anchor not found')
    s = s.replace(anchor, '# Android: disable optional Windows-only diagnostic headers in the isolated worktree.\n'
                  + cmd + '\n\n' + anchor, 1)
    p.write_text(s, encoding='utf-8')
print('OK: diagnostic patch will run after worktree preparation')
