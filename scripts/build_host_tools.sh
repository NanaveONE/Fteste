#!/usr/bin/env bash
# Build native Linux host tools needed BEFORE cross-compiling the Android game.
# Does NOT download or include Fable II assets, and does not build an APK.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for tool in cmake ninja clang clang++ clang-19 clang++-19 python3; do
  command -v "$tool" >/dev/null || { echo "BLOCKED: missing host tool $tool" >&2; exit 2; }
done
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo 'BLOCKED: Linux x86_64 host required. For Android/Termux use GitHub Actions or Linux machine.' >&2
  exit 2
}
sdk="${REXSDK_DIR:-$root/build/deps/rexglue-xerenge}"
xenos="${XENOS_RECOMP_ROOT:-$root/build/deps/XenosRecomp-xerenge}"
xerenge="$root/external/Xerenge"
[[ -f "$sdk/CMakePresets.json" && -f "$xenos/XenosRecomp/CMakeLists.txt" && -f "$xerenge/tools/cxx/CMakeLists.txt" ]] || {
  echo 'BLOCKED: Missing Xerenge, SDK, or XenosRecomp sources. Run scripts/setup_gpu_dependencies.sh and initialize submodules.' >&2
  exit 2
}
# Port Fable's clocked audio fallback into the ignored Android SDK clone
# before any host/Android build, preserving the original checkout.
if [[ ! -f "$sdk/include/rex/audio/fable_clocked_audio_sink.h" ]]; then
  python3 "$root/scripts/port_fable_audio_sdk.py" --sdk "$sdk" --root "$root"
fi
# A stale or partially-applied SDK overlay must never pass through to an APK.
cmp -s "$root/port/sdk/fable_clocked_audio_sink.h" \
  "$sdk/include/rex/audio/fable_clocked_audio_sink.h" || {
    echo 'BLOCKED: Fable audio header differs from the pinned port source' >&2; exit 2;
  }
grep -q 'Fable II silent audio completion permit failed' \
  "$sdk/src/audio/sdl/sdl_audio_driver.cpp" || {
    echo 'BLOCKED: Fable Android audio fallback not applied to the SDK source' >&2; exit 2;
  }
# Xerenge tools CMake target is xerenge_tool_dump_xex, NOT dump_xex_image.
tools_build="$root/build/deps/xerenge-tools"
cmake -S "$xerenge/tools/cxx" -B "$tools_build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++
cmake --build "$tools_build" --target xerenge_tool_dump_xex \
  xerenge_tool_rehost xerenge_tool_wrap_vs xerenge_tool_wrap_ps \
  xerenge_tool_prepare_aux --parallel "${BUILD_JOBS:-2}"

xenos_build="$root/build/deps/xenos-build"
cmake -S "$xenos" -B "$xenos_build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build "$xenos_build" --target XenosRecomp --parallel "${BUILD_JOBS:-2}"

# Linux ReXGlue codegen is a HOST binary; Android NDK binaries cannot run on x86_64.
# clang++ 18 lacks the __cpp_concepts level required by libstdc++ <expected>.
python3 "$root/scripts/check_fable_codegen_cpp23.py" --cc clang-19 --cxx clang++-19
cmake --preset linux-amd64 -S "$sdk" \
  -DCMAKE_C_COMPILER=/usr/bin/clang-19 \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++-19
# Avoid silently reusing a cached LLVM 18 compiler from a previous build.
grep -Eq '^CMAKE_CXX_COMPILER:(FILEPATH|STRING)=/usr/bin/clang\+\+-19$' \
  "$sdk/out/build/linux-amd64/CMakeCache.txt" || {
    echo 'BLOCKED: the Linux ReXGlue CMake cache is not configured for Clang 19' >&2
    echo 'Move aside the old sdk/out/build/linux-amd64 cache and retry.' >&2
    exit 2
  }
cmake --build "$sdk/out/build/linux-amd64" --config Release --target rexglue --parallel "${BUILD_JOBS:-2}"

# Upstream CMakeLists.txt sets CMAKE_RUNTIME_OUTPUT_DIRECTORY to
# "${REXGLUE_ROOT}/out/${REX_PLATFORM}", i.e. out/linux-amd64/Release
# with Ninja Multi-Config. Looking under out/build/... alone loses the binary.
mapfile -t codegen_candidates < <(find "$sdk/out/linux-amd64" -maxdepth 3 -type f \
  -name rexglue -path '*/Release/*' -print | sort)
if [[ "${#codegen_candidates[@]}" != 1 ]]; then
  printf 'BLOCKED: expected one Release host rexglue executable, found %s\n' "${#codegen_candidates[@]}" >&2
  printf '%s\n' "${codegen_candidates[@]}" >&2
  exit 2
fi
host_codegen="${codegen_candidates[0]}"
translator="$xenos_build/XenosRecomp/XenosRecomp"
dumper="$tools_build/dump_xex_image"
for exe in "$host_codegen" "$translator" "$dumper"; do
  [[ -x "$exe" ]] || { echo "BLOCKED: host tool not executable: $exe" >&2; exit 2; }
done
"$host_codegen" --version
# Print reusable exports without writing them to GitHub.
printf '\nHost tools generated. Export these for the next steps:\n'
printf 'export FABLE2_CODEGEN_TOOL=%q\n' "$host_codegen"
printf 'export FABLE2_XEX_DUMPER=%q\n' "$dumper"
printf 'export FABLE2_SHADER_TRANSLATOR=%q\n' "$translator"
printf 'export FABLE2_SHADER_HEADER=%q\n' "$xenos/XenosRecomp/shader_common.h"
printf 'export FABLE2_SHADER_REHOST=%q\n' "$tools_build/rehost_runtime_shader"
printf 'export FABLE2_SHADER_WRAP_VS=%q\n' "$tools_build/wrap_runtime_vertex_shader"
printf 'export FABLE2_SHADER_WRAP_PS=%q\n' "$tools_build/wrap_runtime_pixel_shader"
printf 'export FABLE2_SHADER_RENAME=%q\n' "$tools_build/prepare_aux_shader_cache"
