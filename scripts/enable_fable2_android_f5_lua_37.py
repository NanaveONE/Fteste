#!/usr/bin/env python3
"""Idempotently wire the F5 Lua link-fix into the existing native build."""
from pathlib import Path

TARGET = Path('scripts/build_android_native.sh')
ANCHOR = 'python3 "$root/scripts/fix_fable2_android_diagnostics_33.py" --worktree "$work"'
COMMAND = 'python3 "$root/scripts/fix_fable2_android_f5_lua_37.py" --worktree "$work"'


def enable(content: str) -> str:
    if content.count(COMMAND) == 1:
        return content
    if COMMAND in content:
        raise ValueError('Duplicate or malformed patch 37 invocation')
    if content.count(ANCHOR) != 1:
        raise ValueError('Expected exactly one diagnostics patch 33 call')
    return content.replace(ANCHOR, ANCHOR + '\n\n# F5 Lua host probe depends on excluded Windows diagnostics; drop it on Android.\n' + COMMAND, 1)


def main() -> None:
    if not Path('scripts/fix_fable2_android_f5_lua_37.py').is_file():
        raise SystemExit('BLOCKED: missing patch 37 script')
    if not TARGET.is_file():
        raise SystemExit('BLOCKED: run from the root of Fteste')
    old = TARGET.read_text(encoding='utf-8')
    try:
        new = enable(old)
    except ValueError as exc:
        raise SystemExit(f'BLOCKED: {exc}') from exc
    if new != old:
        TARGET.write_text(new, encoding='utf-8')
    print('OK: patch 37 integrated into build_android_native.sh')


if __name__ == '__main__':
    main()
