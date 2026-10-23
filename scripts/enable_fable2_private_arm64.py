#!/usr/bin/env python3
"""Integrate private generated C++ import into the real Fable II Android NDK build.

Run once in Fteste, commit this script and the patched build script only. NEVER
commit build/ or the user-provided source archive.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

TARGET = Path('scripts/build_android_native.sh')

# Old anchors are from the pinned Fteste build_android_native.sh, current 2026-10-22.
REPLACEMENTS = [
    (
        ': "${FABLE2_CODEGEN_TOOL:?Set FABLE2_CODEGEN_TOOL to matching executable host codegen binary}"',
        'if [[ -z "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then\n'
        '    : "${FABLE2_CODEGEN_TOOL:?Set FABLE2_CODEGEN_TOOL to matching executable host codegen binary}"\n'
        'fi',
    ),
    (
        '[[ -f "$FABLE2_GAME_ROOT/default.xex" && -d "$FABLE2_GAME_ROOT/data" ]] || {\n'
        "    echo 'Expected extracted game folder: default.xex plus data/' >&2; exit 1;\n}",
        '[[ -f "$FABLE2_GAME_ROOT/default.xex" ]] || {\n'
        "    echo 'BLOCKED: private Fable II default.xex missing' >&2; exit 2;\n}\n"
        'if [[ -z "${FABLE2_PRIVATE_CPP_ZIP:-}" && ! -d "$FABLE2_GAME_ROOT/data" ]]; then\n'
        "    echo 'BLOCKED: live codegen requires extracted data/; imported C++ does not' >&2; exit 2;\nfi",
    ),
    (
        '[[ -d "$REXSDK_DIR/include/rex" && -x "$FABLE2_CODEGEN_TOOL" ]] || {\n'
        "    echo 'SDK tree or executable host ReXGlue code generator missing' >&2; exit 1;\n}",
        '[[ -d "$REXSDK_DIR/include/rex" ]] || {\n'
        "    echo 'BLOCKED: Android-compatible ReXGlue SDK source missing' >&2; exit 2;\n}\n"
        'if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then\n'
        '    [[ -s "$FABLE2_PRIVATE_CPP_ZIP" ]] || { echo "BLOCKED: private C++ ZIP missing" >&2; exit 2; }\n'
        'else\n'
        '    [[ -x "$FABLE2_CODEGEN_TOOL" ]] || { echo "BLOCKED: host Codegen missing" >&2; exit 2; }\n'
        'fi',
    ),
    (
        'FABLE2_CODEGEN_TOOL="$(realpath "$FABLE2_CODEGEN_TOOL")"',
        'if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then\n'
        '    FABLE2_PRIVATE_CPP_ZIP="$(realpath "$FABLE2_PRIVATE_CPP_ZIP")"\n'
        'else\n'
        '    FABLE2_CODEGEN_TOOL="$(realpath "$FABLE2_CODEGEN_TOOL")"\n'
        'fi',
    ),
    (
        '    -DANDROID_STL=c++_shared -DREXGLUE_ARM64_MARCH=armv8-a \\',
        '    -DANDROID_STL=c++_shared -DREXGLUE_ARM64_MARCH=armv8-a \\\n'
        '    -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \\\n'
        "    '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384' \\",
    ),
    (
        '    -DFABLE2_CODEGEN_TOOL="$FABLE2_CODEGEN_TOOL"',
        '    -DFABLE2_CODEGEN_TOOL= \\\n'
        '    -DREXGLUE_CODEGEN="${FABLE2_CODEGEN_TOOL:-}" \\\n'
        '    -DFABLE2_PRIVATE_CPP_IMPORTED="$private_cpp_mode"',
    ),
]

CODEGEN_START = '# The upstream generated/rexglue.cmake includes sources.cmake only at'
CODEGEN_END = '# The game target and recompilation object library both use this SDK checkout;'
CODEGEN_PREFIX = '''private_cpp_mode=OFF
if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then
    private_cpp_mode=ON
    echo '[guest] Importing verified private Fable II C++ into ignored build/ worktree'
    python3 "$root/scripts/import_fable2_guest_cpp_private.py" \\
        --repo-root "$root" \\
        --worktree "$work" \\
        --archive "$FABLE2_PRIVATE_CPP_ZIP" \\
        --xex "$FABLE2_GAME_ROOT/default.xex" \
        --sdk "$REXSDK_DIR"
    [[ -s "$work/generated/default/codegen.build.stamp" ]] || {
        echo 'BLOCKED: guest codegen frozen stamp missing' >&2; exit 2;
    }
    [[ -s "$work/generated/default/sources.cmake" ]] || {
        echo 'BLOCKED: original generated source index missing' >&2; exit 2;
    }
else
'''

FINISH_ANCHOR = 'echo \'Native compile command completed. This does NOT prove Fable II is playable.\''
FINISH_NEW = '''# Fail closed if the actual guest library was not produced, is not AArch64,
# or is incompatible with Android 16 KiB page-size devices.
game_so="$build/libfable2.so"
if [[ ! -s "$game_so" ]]; then
    mapfile -d '' -t candidates < <(find "$build" -type f -name libfable2.so -print0)
    if [[ "${#candidates[@]}" != 1 ]]; then
        echo "BLOCKED: expected one real libfable2.so in $build; found ${#candidates[@]}" >&2
        exit 2
    fi
    cp -- "${candidates[0]}" "$game_so"
fi
python3 "$root/scripts/check_android_16k_alignment.py" --file "$game_so" \
    --report "$root/build/fable2-guest-arm64-alignment.json"
readelf_bin="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
[[ -x "$readelf_bin" ]] || { echo 'BLOCKED: llvm-readelf missing from NDK' >&2; exit 2; }
"$readelf_bin" --dyn-syms "$game_so" | grep -Eq 'FUNC +GLOBAL +DEFAULT +[0-9]+ +SDL_main($|[[:space:]])' || {
    echo 'BLOCKED: libfable2.so does not export SDL_main for SDLActivity' >&2; exit 2;
}
echo "OK: verified real ARM64 guest library at $game_so"
''' + FINISH_ANCHOR


def patch_text(content: str) -> str:
    if 'private_cpp_mode=OFF\nif [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]' in content:
        if 'check_android_16k_alignment.py" --file "$game_so"' in content:
            return content
        raise ValueError('Partially applied private ARM64 patch detected')
    for before, after in REPLACEMENTS:
        if content.count(before) != 1:
            raise ValueError(f'Expected exactly one upstream anchor: {before[:80]!r}')
        content = content.replace(before, after)
    if content.count(CODEGEN_START) != 1 or content.count(CODEGEN_END) != 1:
        raise ValueError('Upstream Codegen block changed; fail closed')
    a = content.index(CODEGEN_START)
    b = content.index(CODEGEN_END)
    old = content[a:b]
    if '"$FABLE2_CODEGEN_TOOL" codegen' not in old or 'sources.cmake' not in old:
        raise ValueError('Upstream Codegen validation not recognized')
    # Preserve original live-Codegen logic unchanged, only place under else.
    content = content[:a] + CODEGEN_PREFIX + old + 'fi\n\n' + content[b:]
    if content.count(FINISH_ANCHOR) != 1:
        raise ValueError('Missing native ELF verification anchor')
    return content.replace(FINISH_ANCHOR, FINISH_NEW)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    path = a.root / TARGET
    try:
        original = path.read_text(encoding='utf-8')
        new = patch_text(original)
        if a.check and new != original:
            raise ValueError('Patch not applied yet')
        if new != original and not a.check:
            path.write_text(new, encoding='utf-8')
            print('UPDATED:', path)
        else:
            print('VERIFIED:', path)
    except (OSError, ValueError) as error:
        print('BLOCKED:', error, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
