#!/usr/bin/env bash
# Build the REAL XenosRecomp/DXC host translator and validate Fable II SBK output.
# All copyrighted shader data remains in private ignored build/ directories.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo 'Usage: bash scripts/translate_fable_sbk_real.sh Shaders.sbk [ShadersRelease.sbk]' >&2
  exit 2
fi
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo 'BLOCKED: build on a Linux x86_64 host, not Termux/Android ARM64' >&2; exit 2;
}
for tool in cmake ninja python3; do
  command -v "$tool" >/dev/null || { echo "BLOCKED: missing ${tool}" >&2; exit 2; }
done
# Option A: downloadable compiler artifact from the public GitHub Actions
# workflow, containing XenosRecomp, its DXC .so and shader_common.h.
# Option B: build XenosRecomp and its vendored DXC sources locally.
mkdir -p "$root/build/logs"
out="${FABLE2_SHADER_DIR:-$root/build/fable2-shaders}"
[[ ! -e "$out" ]] || {
  echo "BLOCKED: ${out} exists; preserve prior results, move aside to retry" >&2
  exit 2
}
for file in "$@"; do
  [[ -s "$file" ]] || { echo "BLOCKED: missing/private shader bank: $file" >&2; exit 2; }
done
if [[ -n "${XENOSRECOMP_HOST_DIR:-}" ]]; then
  toolroot="$(realpath "$XENOSRECOMP_HOST_DIR")"
  exe="$toolroot/XenosRecomp"
  header="$toolroot/shader_common.h"
  [[ -x "$exe" && -s "$header" ]] || {
    echo 'BLOCKED: tool artifact must contain executable XenosRecomp and shader_common.h' >&2
    exit 2
  }
  export LD_LIBRARY_PATH="$toolroot${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  echo "Using real precompiled host translator: $exe"
else
  xenos="${XENOS_RECOMP_ROOT:-$root/build/deps/XenosRecomp-xerenge}"
  [[ -f "$xenos/XenosRecomp/CMakeLists.txt" && -f "$xenos/thirdparty/dxc-bin/CMakeLists.txt" \
      && -f "$xenos/thirdparty/smol-v/source/smolv.cpp" ]] || {
    echo 'BLOCKED: XenosRecomp source and dxc-bin/smol-v submodules missing.' >&2
    echo 'Run scripts/setup_gpu_dependencies.sh (requires network) OR provide XENOSRECOMP_HOST_DIR' >&2
    exit 2
  }
  build="$root/build/host-xenosrecomp"
  compiler="${HOST_CXX:-clang++}"
  command -v "$compiler" >/dev/null || { echo "BLOCKED: compiler $compiler absent" >&2; exit 2; }
  cmake -S "$xenos" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_COMPILER="$compiler" 2>&1 | tee "$root/build/logs/xenos-configure.log"
  cmake --build "$build" --target XenosRecomp --parallel "${BUILD_JOBS:-2}" \
        2>&1 | tee "$root/build/logs/xenos-build.log"
  exe="$build/XenosRecomp/XenosRecomp"
  header="$xenos/XenosRecomp/shader_common.h"
  [[ -x "$exe" ]] || { echo "BLOCKED: real XenosRecomp missing at $exe" >&2; exit 2; }
fi
python3 "$root/scripts/generate_fable_shaders.py" --shader-banks "$@" \
    --translator "$exe" --header "$header" \
    --output "$out" 2>&1 | tee "$root/build/logs/fable-shader-translation.log"
python3 "$root/scripts/validate_xenosrecomp_cache.py" \
    --cache "$out/shader_cache.cpp" --scan-dir "$out/xenos-scan" \
    --min-coverage 1.0 --report "$out/spirv-coverage-report.json"
cat <<EOF
SUCCESS: genuine XenosRecomp produced SPIR-V for every extracted SBK container.
C++ cache: $out/shader_cache.cpp
Coverage report: $out/spirv-coverage-report.json
NEXT: build GPU plugin; SPIR-V is NOT evidence that EDRAM/graphics already work.
EOF
