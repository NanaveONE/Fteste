#!/usr/bin/env python3
"""Isolate Windows F5-Lua developer probe from Android's genuine guest code.

The F5 probe calls inline helpers from fable2_text_append.h. The optional
text-append diagnostic is disabled on Android, leaving link-time undefined
symbols. Keep the original Windows feature; Android uses generated guest
LuaBind_RunScript_82806168 rather than the host diagnostic override.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MAIN = Path('src/main.cpp')
HEADER = Path('src/input/keyboard_gamepad.h')
INCLUDE = '#include "fable2_f5_lua.h"'
REPLACEMENT = ('#if !defined(__ANDROID__)  // FTESTE_ANDROID_F5_LUA_37\n'
               '#include "fable2_f5_lua.h"\n'
               '#endif  // !__ANDROID__: optional Windows-only F5 Lua diagnostic')
FPS_METER_INCLUDE = '#include "fps_meter.h"'


def patch(root: Path) -> str:
    main_path = root / MAIN
    keyboard_path = root / HEADER
    if not main_path.is_file() or not keyboard_path.is_file():
        raise ValueError('Expected Fable II host files src/main.cpp and src/input/keyboard_gamepad.h')

    s = main_path.read_text(encoding='utf-8')
    keyboard = keyboard_path.read_text(encoding='utf-8')
    if s.count(REPLACEMENT) == 1:
        if s.count('FTESTE_ANDROID_F5_LUA_37') != 1:
            raise ValueError('Duplicate F5 Lua compatibility marker')
        return 'already patched'
    if 'FTESTE_ANDROID_F5_LUA_37' in s:
        raise ValueError('Incomplete F5 Lua compatibility patch')
    if s.count(INCLUDE) != 1:
        raise ValueError(f'Unexpected main.cpp: expected one {INCLUDE}')

    # Stage 33 must have excluded fps_meter.h from the Android main TU: it
    # also includes fable2_f5_lua.h. Do not silently leave that dependency.
    if 'FTESTE_ANDROID_DIAGNOSTICS_33' not in s:
        raise ValueError('Apply diagnostics patch 33 first')
    if '#if !defined(__ANDROID__)\n' + FPS_METER_INCLUDE + '\n#endif' not in s:
        raise ValueError('fps_meter.h is not Android-guarded; potential F5 dependency')

    # The sole Android-facing call to poll_f5() is compiled out upstream by
    # #ifdef _WIN32. Confirm against the pinned source before changing main.
    if keyboard.count('fable2::f5lua::poll_f5();') != 1:
        raise ValueError('Unexpected keyboard_gamepad.h F5 poll references')
    before = keyboard.split('fable2::f5lua::poll_f5();', 1)[0]
    after = keyboard.split('fable2::f5lua::poll_f5();', 1)[1]
    if before.rfind('#ifdef _WIN32') < before.rfind('#endif') or '#endif' not in after:
        raise ValueError('F5 poll is no longer guarded by _WIN32 in keyboard_gamepad.h')

    main_path.write_text(s.replace(INCLUDE, REPLACEMENT, 1), encoding='utf-8')
    return 'patched'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree', required=True, type=Path)
    args = parser.parse_args()
    try:
        print('[f5-lua37]', patch(args.worktree))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f'BLOCKED [f5-lua37]: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
