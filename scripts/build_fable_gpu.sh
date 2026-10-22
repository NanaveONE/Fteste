#!/usr/bin/env bash
# Build the genuine Xerenge Plume renderer plugin with Fable II's shader cache.
# This does NOT claim that all Fable II GPU commands/states are supported.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
: "${ANDROID_NDK_HOME:?Set Android NDK installation path}"
: "${REXSDK_DIR:?Set Android-capable ReXGlue fork path, built with matching game runtime}"
: "${PLUME_ROOT:?Set clone of shipa-2/plume-xerenge}"
: "${XENOS_RECOMP_ROOT:?Set clone of shipa-2/XenosRecomp-xerenge}"
shader_dir="${FABLE2_SHADER_DIR:-$root/build/fable2-shaders}"
shader_cache="$shader_dir/shader_cache.cpp"
shader_report="$shader_dir/fable-shader-report.json"
[[ -s "$shader_cache" && -s "$shader_report" ]] || {
  echo 'BLOCKED: no Fable-specific shader cache. Run scripts/generate_fable_shaders.py first.' >&2
  exit 2
}
[[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ]] || { echo 'Android NDK not installed' >&2; exit 2; }
[[ -d "$REXSDK_DIR/include/rex" && -f "$PLUME_ROOT/CMakeLists.txt" && -f "$XENOS_RECOMP_ROOT/XenosRecomp/shader_common.h" ]] || {
  echo 'BLOCKED: one of the SDK/Plume/XenosRecomp paths is incomplete' >&2; exit 2;
}
for tool in cmake ninja python3; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 2; }; done
python3 - "$shader_report" "$shader_cache" <<'PY'
import hashlib, json, sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
actual = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
if report.get('source_title') != 'Fable II' or report.get('cache_sha256') != actual:
    raise SystemExit('BLOCKED: shader cache provenance mismatch')
PY
# A valid provenance hash does not prove SPIR-V was generated. Check that
# every static container in the private extraction has a valid SPIR-V module.
python3 "$root/scripts/validate_xenosrecomp_cache.py" \
  --cache "$shader_cache" --scan-dir "$shader_dir/xenos-scan" \
  --min-coverage 1.0 --report "$shader_dir/spirv-coverage-report.json"

# Refuse Windows-only SDKs before an expensive Plume cross build. The exact
# same Android SDK checkout must be supplied to build_android_native.sh.
python3 "$root/scripts/audit_android_sdk.py" --sdk "$REXSDK_DIR" \
  --fable-sdk "$root/external/Fable-2-Recomp/thirdparty/rexglue-sdk" \
  --json "$root/build/android-sdk-audit.json"

# The host shader-source metadata table must include HLSL from BOTH caches.
# Two independently generated tables would define FillShaderSourceInfoTable
# twice and cause a duplicate symbol during the .so link.
shader_hlsl="$shader_dir/xenos-hlsl"
if [[ -n "${FABLE2_RUNTIME_SHADER_CACHE_CPP:-}" ]]; then
  runtime_parent="$(dirname "$(realpath "$FABLE2_RUNTIME_SHADER_CACHE_CPP")")"
  runtime_hlsl="$runtime_parent/xenos-hlsl"
  shader_hlsl="$root/build/fable2-shader-hlsl-merged"
  python3 "$root/scripts/merge_fable_shader_sources.py" \
    --static "$shader_dir/xenos-hlsl" --runtime "$runtime_hlsl" \
    --output "$shader_hlsl"
fi

# Copy+patch the draw state logic in a private build output; do not touch
# external/Xerenge. Verify source and patch hashes on subsequent invocations.
plume_overlay="$root/build/fable2-plume-overlay-v2"
python3 "$root/scripts/prepare_fable_plume.py" \
  --xerenge-root "$root/external/Xerenge" --output "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"
cmake -S "$root/port/gpu" -B "$build" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 \
  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS=-march=armv8-a -moutline-atomics' \
  '-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics' \
  -DREXSDK_DIR="$REXSDK_DIR" -DPLUME_ROOT="$PLUME_ROOT" \
  -DXENOS_RECOMP_ROOT="$XENOS_RECOMP_ROOT" \
  -DXERENGE_ROOT="$root/external/Xerenge" \
  -DFABLE2_SHADER_CACHE_CPP="$shader_cache" \
  -DFABLE2_SHADER_HLSL_DIR="$shader_hlsl" \
  -DFABLE2_PLUME_DRAW_CPP="$plume_overlay/plume_draw.cpp" \
  -DFABLE2_PLUME_GRAPHICS_CPP="$plume_overlay/plume_graphics_system.cpp" \
  -DFABLE2_RUNTIME_SHADER_CACHE_CPP="${FABLE2_RUNTIME_SHADER_CACHE_CPP:-}"
cmake --build "$build" --target rexgpu-plume --parallel "${BUILD_JOBS:-2}"
[[ -s "$build/librexgpu-plume.so" ]] || { echo 'Expected GPU library was not created' >&2; exit 2; }
file "$build/librexgpu-plume.so" || true
echo "Compiled GPU plugin: $build/librexgpu-plume.so"
echo 'WARNING: Shader translation is not proof that Fable II draws correctly.'
