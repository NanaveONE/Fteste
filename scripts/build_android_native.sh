#!/usr/bin/env bash
# Cross-build the genuine Fable II ARM64 guest code and host library.
# Requires your compatible local game dump and a source-built Android SDK.
# This does not build a Fable-ready Plume GPU implementation automatically.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

: "${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME to Android NDK installation}"
: "${FABLE2_GAME_ROOT:?Set FABLE2_GAME_ROOT to your extracted legal game content folder}"
: "${REXSDK_DIR:?Set REXSDK_DIR to Android-compatible ReXGlue SDK source tree}"
if [[ -z "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then
    : "${FABLE2_CODEGEN_TOOL:?Set FABLE2_CODEGEN_TOOL to matching executable host codegen binary}"
fi

for exe in cmake ninja python3; do
    command -v "$exe" >/dev/null || { echo "Missing command: $exe" >&2; exit 1; }
done
[[ -f "$FABLE2_GAME_ROOT/default.xex" ]] || {
    echo 'BLOCKED: private Fable II default.xex missing' >&2; exit 2;
}
if [[ -z "${FABLE2_PRIVATE_CPP_ZIP:-}" && ! -d "$FABLE2_GAME_ROOT/data" ]]; then
    echo 'BLOCKED: live codegen requires extracted data/; imported C++ does not' >&2; exit 2;
fi
[[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ]] || {
    echo 'Android NDK CMake toolchain not found' >&2; exit 1;
}
[[ -d "$REXSDK_DIR/include/rex" ]] || {
    echo 'BLOCKED: Android-compatible ReXGlue SDK source missing' >&2; exit 2;
}
if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then
    [[ -s "$FABLE2_PRIVATE_CPP_ZIP" ]] || { echo "BLOCKED: private C++ ZIP missing" >&2; exit 2; }
else
    [[ -x "$FABLE2_CODEGEN_TOOL" ]] || { echo "BLOCKED: host Codegen missing" >&2; exit 2; }
fi
# The codegen is invoked after changing into the isolated source tree.
# Resolve relative user paths now to avoid resolving them inside build/.
if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then
    FABLE2_PRIVATE_CPP_ZIP="$(realpath "$FABLE2_PRIVATE_CPP_ZIP")"
else
    FABLE2_CODEGEN_TOOL="$(realpath "$FABLE2_CODEGEN_TOOL")"
fi
REXSDK_DIR="$(realpath "$REXSDK_DIR")"
FABLE2_GAME_ROOT="$(realpath "$FABLE2_GAME_ROOT")"

work="$root/build/fable2-android-worktree"
if [[ ! -f "$work/CMakeLists.txt" ]]; then
    python3 "$root/scripts/prepare_android_target.py" --source "$root/external/Fable-2-Recomp" \
        --output "$work" --port-root "$root/port"
fi

# Android: disable optional Windows-only diagnostic headers in the isolated worktree.
python3 "$root/scripts/fix_fable2_android_diagnostics_33.py" --worktree "$work"

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

private_cpp_mode=OFF
if [[ -n "${FABLE2_PRIVATE_CPP_ZIP:-}" ]]; then
    private_cpp_mode=ON
    echo '[guest] Importing verified private Fable II C++ into ignored build/ worktree'
    python3 "$root/scripts/import_fable2_guest_cpp_private.py" \
        --repo-root "$root" \
        --worktree "$work" \
        --archive "$FABLE2_PRIVATE_CPP_ZIP" \
        --xex "$FABLE2_GAME_ROOT/default.xex"         --sdk "$REXSDK_DIR"
    [[ -s "$work/generated/default/codegen.build.stamp" ]] || {
        echo 'BLOCKED: guest codegen frozen stamp missing' >&2; exit 2;
    }
    [[ -s "$work/generated/default/sources.cmake" ]] || {
        echo 'BLOCKED: original generated source index missing' >&2; exit 2;
    }
else
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

fi

# The game target and recompilation object library both use this SDK checkout;
# the GPU plugin must use the same checkout and revision too.
python3 "$root/scripts/audit_android_sdk.py" --sdk "$REXSDK_DIR" \
    --fable-sdk "$root/external/Fable-2-Recomp/thirdparty/rexglue-sdk" \
    --json "$root/build/android-sdk-audit.json"

# ImGui is a private SDK transitive header included by rex/rex_app.h.
# The game target does not inherit its include directory automatically.
imgui_header="$(find "$REXSDK_DIR/thirdparty" -type f -name imgui.h -print -quit)"
if [[ -z "$imgui_header" ]]; then
    echo 'BLOCKED: SDK thirdparty/imgui.h missing; check recursive submodules' >&2
    exit 2
fi
imgui_dir="$(dirname "$imgui_header")"
[[ -s "$imgui_dir/imgui.h" ]] || { echo 'BLOCKED: imgui.h empty' >&2; exit 2; }
echo "[android] Dear ImGui include directory: $imgui_dir"

build="$root/build/fable2-android-arm64"
cmake -S "$work" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 \
    -DANDROID_STL=c++_shared -DREXGLUE_ARM64_MARCH=armv8-a \
    -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \
    '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384' \
    '-DCMAKE_C_FLAGS=-march=armv8-a -moutline-atomics' \
    "-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics -I${imgui_dir}" \
    -DFABLE2_PORT_ROOT="$root/port" \
    -DREXSDK_DIR="$REXSDK_DIR" \
    -DFABLE2_CODEGEN_TOOL= \
    -DREXGLUE_CODEGEN="${FABLE2_CODEGEN_TOOL:-}" \
    -DFABLE2_PRIVATE_CPP_IMPORTED="$private_cpp_mode"
cmake --build "$build" --target fable_2 --parallel "${BUILD_JOBS:-2}"

# Fail closed if the actual guest library was not produced, is not AArch64,
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
python3 "$root/scripts/check_android_16k_alignment.py" --file "$game_so"     --report "$root/build/fable2-guest-arm64-alignment.json"
readelf_bin="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
[[ -x "$readelf_bin" ]] || { echo 'BLOCKED: llvm-readelf missing from NDK' >&2; exit 2; }
"$readelf_bin" --dyn-syms "$game_so" | grep -Eq 'FUNC +GLOBAL +DEFAULT +[0-9]+ +SDL_main($|[[:space:]])' || {
    echo 'BLOCKED: libfable2.so does not export SDL_main for SDLActivity' >&2; exit 2;
}
echo "OK: verified real ARM64 guest library at $game_so"
echo 'Native compile command completed. This does NOT prove Fable II is playable.'
echo 'Before packaging you must build a Fable-compatible librexgpu-plume.so'
echo 'and verify the runtime binary ABI with scripts/check_native_libs.py.'
