#!/usr/bin/env bash
# Cross-build the genuine Fable II ARM64 guest code and host library.
# Requires your compatible local game dump and a source-built Android SDK.
# This does not build a Fable-ready Plume GPU implementation automatically.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

: "${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME to Android NDK installation}"
: "${FABLE2_GAME_ROOT:?Set FABLE2_GAME_ROOT to your extracted legal game content folder}"
: "${REXSDK_DIR:?Set REXSDK_DIR to Android-compatible ReXGlue SDK source tree}"
: "${FABLE2_CODEGEN_TOOL:?Set FABLE2_CODEGEN_TOOL to matching executable host codegen binary}"

for exe in cmake ninja python3; do
    command -v "$exe" >/dev/null || { echo "Missing command: $exe" >&2; exit 1; }
done
[[ -f "$FABLE2_GAME_ROOT/default.xex" && -d "$FABLE2_GAME_ROOT/data" ]] || {
    echo 'Expected extracted game folder: default.xex plus data/' >&2; exit 1;
}
[[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ]] || {
    echo 'Android NDK CMake toolchain not found' >&2; exit 1;
}
[[ -d "$REXSDK_DIR/include/rex" && -x "$FABLE2_CODEGEN_TOOL" ]] || {
    echo 'SDK tree or executable host ReXGlue code generator missing' >&2; exit 1;
}
# The codegen is invoked after changing into the isolated source tree.
# Resolve relative user paths now to avoid resolving them inside build/.
FABLE2_CODEGEN_TOOL="$(realpath "$FABLE2_CODEGEN_TOOL")"
REXSDK_DIR="$(realpath "$REXSDK_DIR")"
FABLE2_GAME_ROOT="$(realpath "$FABLE2_GAME_ROOT")"

work="$root/build/fable2-android-worktree"
if [[ ! -f "$work/CMakeLists.txt" ]]; then
    python3 "$root/scripts/prepare_android_target.py" --source "$root/external/Fable-2-Recomp" \
        --output "$work" --port-root "$root/port"
fi

# Codegen and Fable's Lua staging operate on the *worktree*, never on the
# original game dump. Keep copies in ignored build/ to avoid mutating content.
if [[ -f "$work/default.xex" ]]; then
    cmp -s -- "$FABLE2_GAME_ROOT/default.xex" "$work/default.xex" || {
        echo 'BLOCKED: another XEX exists in worktree. Refusing to mix game versions.' >&2; exit 2;
    }
else
    cp -- "$FABLE2_GAME_ROOT/default.xex" "$work/default.xex"
fi
mkdir -p "$work/data"
if [[ -f "$FABLE2_GAME_ROOT/data/dir.manifest" ]]; then
    cp -- "$FABLE2_GAME_ROOT/data/dir.manifest" "$work/data/dir.manifest"
fi

# The upstream generated/rexglue.cmake includes sources.cmake only at
# CONFIGURE time. Run host codegen before CMake, otherwise the Fable guest
# object library would not exist and an empty launcher could be packaged.
# Generate on each invocation to fail fast when guest inputs are wrong.
echo '[codegen] Generating Fable II guest sources on the build host'
(cd "$work" && "$FABLE2_CODEGEN_TOOL" codegen "$work/fable_2_manifest.toml")
sources_index="$work/generated/default/sources.cmake"
[[ -s "$sources_index" ]] || { echo 'BLOCKED: ReXGlue did not generate sources.cmake' >&2; exit 2; }
# Fail closed if the input contains a bogus empty list.
python3 - "$sources_index" <<'PYCODEGEN'
from pathlib import Path
import re, sys
text = Path(sys.argv[1]).read_text(encoding='utf-8')
if not re.search(r'set\s*\(\s*GENERATED_SOURCES\b', text, re.I) or not re.search(r'\.cpp\b', text):
    sys.exit('BLOCKED: sources.cmake contains no generated guest .cpp files')
PYCODEGEN

# The game target and recompilation object library both use this SDK checkout;
# the GPU plugin must use the same checkout and revision too.
python3 "$root/scripts/audit_android_sdk.py" --sdk "$REXSDK_DIR" \
    --fable-sdk "$root/external/Fable-2-Recomp/thirdparty/rexglue-sdk" \
    --json "$root/build/android-sdk-audit.json"

build="$root/build/fable2-android-arm64"
cmake -S "$work" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 \
    -DANDROID_STL=c++_shared -DREXGLUE_ARM64_MARCH=armv8-a \
    '-DCMAKE_C_FLAGS=-march=armv8-a -moutline-atomics' \
    '-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics' \
    -DFABLE2_PORT_ROOT="$root/port" \
    -DREXSDK_DIR="$REXSDK_DIR" \
    -DFABLE2_CODEGEN_TOOL="$FABLE2_CODEGEN_TOOL"
cmake --build "$build" --target fable_2 --parallel "${BUILD_JOBS:-2}"

echo 'Native compile command completed. This does NOT prove Fable II is playable.'
echo 'Before packaging you must build a Fable-compatible librexgpu-plume.so'
echo 'and verify the runtime binary ABI with scripts/check_native_libs.py.'
