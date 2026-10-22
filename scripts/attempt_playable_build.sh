#!/usr/bin/env bash
# Real, fail-closed build chain: Fable II codegen -> ARM64 .so -> Fable shaders
# -> Plume .so -> ELF dependencies -> signed APK. No dummy binary is generated.
# Success means an APK was packaged, NOT that gameplay works on a phone.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
usage() {
  cat <<'HELP'
Usage: bash scripts/attempt_playable_build.sh --check | --build
  --check   Report missing game/toolchain inputs, without generating anything.
  --build   Try to compile an actual Fable II APK from YOUR local legal game dump.

Linux x86_64 + clang, cmake, ninja, JDK, Android SDK/NDK required.
Required env: FABLE2_GAME_ROOT, ANDROID_NDK_HOME, ANDROID_HOME,
  REXSDK_DIR, PLUME_ROOT, XENOS_RECOMP_ROOT, FABLE2_CODEGEN_TOOL,
  FABLE2_SHADER_TRANSLATOR; SBK shader files in data/shaders are required.
Optional: SDL_JAVA_DIR, FABLE2_SHADER_HEADER, REXRUNTIME_LIB,
  FABLE2_LIBRARY_SEARCH_DIRS (colon-separated), FABLE2_EXTRA_LIBS (colon-separated), BUILD_JOBS.

Run scripts/setup_gpu_dependencies.sh and scripts/build_host_tools.sh first.
Nothing uploads proprietary game files. Build outputs are ignored in build/.
HELP
}
[[ $# == 1 ]] || { usage >&2; exit 2; }
case "$1" in
  --check) exec python3 "$root/scripts/playable_preflight.py" --json "$root/build/playable-preflight.json" ;;
  --build) ;;
  *) usage >&2; exit 2 ;;
esac
python3 "$root/scripts/playable_preflight.py" --json "$root/build/playable-preflight.json"
: "${FABLE2_GAME_ROOT:?}"
: "${ANDROID_NDK_HOME:?}"
: "${ANDROID_HOME:?}"
: "${REXSDK_DIR:?}"
: "${PLUME_ROOT:?}"
: "${XENOS_RECOMP_ROOT:?}"
: "${FABLE2_CODEGEN_TOOL:?}"
: "${FABLE2_SHADER_TRANSLATOR:?}"
# Fable II shaders reside in data/shaders/*.sbk, not default.xex.
# Use both banks when present; containers are deduplicated by SHA-256.
shader_dir="$root/build/fable2-shaders"
mapfile -d '' -t shader_banks < <(python3 "$root/scripts/find_fable_shader_banks.py" \
  --game-root "$FABLE2_GAME_ROOT" --print0)
if [[ ${#shader_banks[@]} -eq 0 ]]; then
  echo 'BLOCKED: Fable II .sbk shader banks missing from data/shaders/' >&2
  exit 2
fi
if [[ -e "$shader_dir" ]]; then
  # A cache is trusted only if every original private SBK still matches.
  python3 - "$shader_dir" "${shader_banks[@]}" <<'PYSBKVERIFY'
import hashlib, json, sys
from pathlib import Path
folder = Path(sys.argv[1]); banks = list(map(Path, sys.argv[2:]))
report_file = folder / 'fable-shader-report.json'
cache = folder / 'shader_cache.cpp'
if not report_file.is_file() or not cache.is_file():
    raise SystemExit('BLOCKED: partial shader cache; move aside after inspection')
report = json.loads(report_file.read_text(encoding='utf-8'))
recorded = {bank['filename'].casefold(): bank['sha256']
            for bank in report.get('shader_banks', [])}
actual = {bank.name.casefold(): hashlib.sha256(bank.read_bytes()).hexdigest()
          for bank in banks}
if report.get('source_title') != 'Fable II' or report.get('input_kind') != 'shader_banks' \
   or not actual or recorded != actual or report.get('cache_sha256') != hashlib.sha256(cache.read_bytes()).hexdigest():
    raise SystemExit('BLOCKED: shader cache provenance differs from local Fable II banks')
print('OK: existing static shader cache matches original SBK inputs')
PYSBKVERIFY
else
  python3 "$root/scripts/generate_fable_shaders.py" \
    --shader-banks "${shader_banks[@]}" \
    --output "$shader_dir" \
    --translator "$FABLE2_SHADER_TRANSLATOR" \
    --header "${FABLE2_SHADER_HEADER:-$XENOS_RECOMP_ROOT/XenosRecomp/shader_common.h}"
fi
# XenosRecomp may return exit status 0 even after skipping unsupported shaders.
# Audit EVERY generated SPIR-V module and require coverage of every private
# static SBK container before attempting ARM64 build. Reject stale caches too.
python3 "$root/scripts/validate_xenosrecomp_cache.py" \
  --cache "$shader_dir/shader_cache.cpp" --scan-dir "$shader_dir/xenos-scan" \
  --min-coverage 1.0 --report "$shader_dir/spirv-coverage-report.json"
# Keep the host/game/plugin on exactly one Android source SDK; do not use a
# prebuilt Windows Fable runtime even when its numeric plugin ABI matches.
if [[ -z "${REXRUNTIME_LIB:-}" ]]; then
  bash "$root/scripts/build_rexglue_android_sdk.sh"
  mapfile -t runtime_candidates < <(find "$root/build/rexglue-android-arm64" \
    -type f -name librexruntime.so -print)
  if [[ ${#runtime_candidates[@]} != 1 ]]; then
    echo 'BLOCKED: no unique ReXGlue ARM64 runtime built' >&2
    exit 2
  fi
  export REXRUNTIME_LIB="${runtime_candidates[0]}"
fi
bash "$root/scripts/build_android_native.sh"
# Optional second pass: user-captured runtime shaders are translated offline
# and rebuilt into the Plume plugin with the Bootstrap symbol set.
runtime_shaders="$root/build/fable2-runtime-shaders"
if [[ -d "$runtime_shaders" ]]; then
  : "${FABLE2_DECODED_GUEST_IMAGE:?Required to verify runtime shader captures against your decoded Fable II XEX}"
  python3 - "$runtime_shaders" "$FABLE2_DECODED_GUEST_IMAGE" <<'PYRUNTIME'
from pathlib import Path
import json, hashlib, sys
runtime, guest_image = map(Path, sys.argv[1:])
report = json.loads((runtime / 'runtime-shader-report.json').read_text())
if not guest_image.is_file():
    raise SystemExit('BLOCKED: decoded XEX image missing for runtime capture verification')
cache = runtime / 'shader_cache_runtime.cpp'
if not cache.is_file() or report.get('shader_cache_sha256') != hashlib.sha256(cache.read_bytes()).hexdigest() \
   or report.get('guest_image_sha256') != hashlib.sha256(guest_image.read_bytes()).hexdigest():
    raise SystemExit('BLOCKED: stale or mixed runtime shader cache')
print('OK: linking Fable II runtime-captured shaders into Plume')
PYRUNTIME
  export FABLE2_RUNTIME_SHADER_CACHE_CPP="$runtime_shaders/shader_cache_runtime.cpp"
fi
bash "$root/scripts/build_fable_gpu.sh"
: "${REXRUNTIME_LIB:?Set REXRUNTIME_LIB to the ARM64 librexruntime.so from the SAME ReXGlue SDK build}"
cxx="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so"
readelf="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
args=(--game-lib "$root/build/fable2-android-arm64/libfable2.so"
      --gpu-lib "$root/build/fable2-gpu-android-arm64/librexgpu-plume.so"
      --runtime-lib "$REXRUNTIME_LIB"
      --cxx-lib "$cxx"
      --readelf "$readelf"
      --output "$root/build/android-native-stage")
if [[ -n "${FABLE2_LIBRARY_SEARCH_DIRS:-}" ]]; then
  IFS=: read -r -a dirs <<< "$FABLE2_LIBRARY_SEARCH_DIRS"
  for dir in "${dirs[@]}"; do [[ -n "$dir" ]] && args+=(--search-dir "$dir"); done
fi
if [[ -n "${FABLE2_EXTRA_LIBS:-}" ]]; then
  IFS=: read -r -a extras <<< "$FABLE2_EXTRA_LIBS"
  for lib in "${extras[@]}"; do [[ -n "$lib" ]] && args+=(--extra-lib "$lib"); done
fi
if [[ -e "$root/build/android-native-stage" ]]; then
  echo 'BLOCKED: old native stage exists. Remove build/android-native-stage after confirming it is disposable.' >&2
  exit 2
fi
python3 "$root/scripts/stage_android_libs.py" "${args[@]}"
SDL_JAVA_DIR="${SDL_JAVA_DIR:-$REXSDK_DIR/thirdparty/sdl3/android-project/app/src/main/java}" \
NATIVE_LIB_DIR="$root/build/android-native-stage" \
bash "$root/scripts/package_android_apk.sh"
echo 'APK signed; gameplay still needs actual device tests (render, input, audio, save, stability).'
