#!/usr/bin/env bash
# Build native Linux host tools needed BEFORE cross-compiling the Android game.
# Does NOT download or include Fable II assets, and does not build an APK.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for tool in cmake ninja clang clang++ python3; do
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
# Xerenge tools CMake target is xerenge_tool_dump_xex, NOT dump_xex_image.
tools_build="$root/build/deps/xerenge-tools"
cmake -S "$xerenge/tools/cxx" -B "$tools_build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++
cmake --build "$tools_build" --target xerenge_tool_dump_xex --parallel "${BUILD_JOBS:-2}"

xenos_build="$root/build/deps/xenos-build"
cmake -S "$xenos" -B "$xenos_build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build "$xenos_build" --target XenosRecomp --parallel "${BUILD_JOBS:-2}"

# Linux ReXGlue codegen is a HOST binary; Android NDK binaries cannot run on x86_64.
cmake --preset linux-amd64 -S "$sdk"
cmake --build "$sdk/out/build/linux-amd64" --config Release --target rexglue --parallel "${BUILD_JOBS:-2}"

host_codegen="$sdk/out/linux-amd64/Release/rexglue"
translator="$xenos_build/XenosRecomp/XenosRecomp"
dumper="$tools_build/dump_xex_image"
for exe in "$host_codegen" "$translator" "$dumper"; do
  [[ -x "$exe" ]] || { echo "BLOCKED: host tool not executable: $exe" >&2; exit 2; }
done
# Print reusable exports without writing them to GitHub.
printf '\nHost tools generated. Export these for the next steps:\n'
printf 'export FABLE2_CODEGEN_TOOL=%q\n' "$host_codegen"
printf 'export FABLE2_XEX_DUMPER=%q\n' "$dumper"
printf 'export FABLE2_SHADER_TRANSLATOR=%q\n' "$translator"
printf 'export FABLE2_SHADER_HEADER=%q\n' "$xenos/XenosRecomp/shader_common.h"
