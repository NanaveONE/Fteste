#!/usr/bin/env python3
"""Guard Windows-only optional diagnostics in the isolated Fable II Android worktree.

Never changes the source submodule or private game content.
"""
from pathlib import Path
import argparse

OPTIONAL = (
    'fps_meter.h', 'fable2_text_probe.h', 'fable2_glyph_probe.h',
    'fable2_hotfuncs.h', 'fable2_heap_scan.h', 'fable2_text_append.h',
    'fable2_menu_probe.h', 'fable2_modmenu.h',
)
MARKER = '// FTESTE_ANDROID_DIAGNOSTICS_33'

def patch_main(path: Path):
    source = path.read_text(encoding='utf-8')
    if MARKER in source:
        return 'already patched'
    for name in OPTIONAL:
        line = '#include "' + name + '"'
        if source.count(line) != 1:
            raise ValueError(f'Unexpected main.cpp: expected one {line}')
    # Preserve stateprobe: fable_2_app.h calls its runtime functions.
    # Windows-only diagnostics are debug instrumentation, not guest codegen.
    for name in OPTIONAL:
        line = '#include "' + name + '"'
        source = source.replace(line, '#if !defined(__ANDROID__)\n' + line + '\n#endif  // !__ANDROID__', 1)
    source = source.replace('#if !defined(__ANDROID__)\n', '#if !defined(__ANDROID__)\n', 1)
    source = MARKER + '\n' + source
    path.write_text(source, encoding='utf-8')
    return 'patched'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worktree', type=Path, default=Path('build/fable2-android-worktree'))
    args = parser.parse_args()
    path = args.worktree / 'src/main.cpp'
    if not path.is_file():
        parser.error(f'Worktree main.cpp missing: {path}')
    print(patch_main(path))

if __name__ == '__main__':
    main()
