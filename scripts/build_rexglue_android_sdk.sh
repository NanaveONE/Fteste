#!/usr/bin/env bash
# Build the real Android ReXGlue runtime from the SAME checkout passed to
# the Fable II guest and the Plume GPU plugin. No game assets are needed.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
: "${ANDROID_NDK_HOME:?Android NDK required}"
sdk="${REXSDK_DIR:-$root/build/deps/rexglue-xerenge}"
[[ -f "$sdk/CMakeLists.txt" && -f "$sdk/src/core/main_android.cpp" ]] || {
  echo 'BLOCKED: Android ReXGlue sources missing. Run scripts/setup_gpu_dependencies.sh first.' >&2; exit 2;
}
[[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ]] || {
  echo 'BLOCKED: Android NDK CMake toolchain missing.' >&2; exit 2;
}
for command in cmake ninja python3; do command -v "$command" >/dev/null || {
  echo "BLOCKED: missing $command" >&2; exit 2;
}; done
sdk="$(cd "$sdk" && pwd)"
: "${REXSDK_DIR:=$sdk}"
# # FTESTE_REXRUNTIME_16K_39 SDK revision must exactly match the already-built libfable2.so.
revision="$(git -C "$sdk" rev-parse HEAD)" || {
  echo 'BLOCKED: ReXGlue SDK must be a git checkout' >&2; exit 2;
}
if [[ "$revision" != "3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b" ]]; then
  echo "BLOCKED: wrong ReXGlue SDK revision $revision; expected 3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b" >&2
  exit 2
fi
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
# The Android NDK r27 libc++ does not implement floating std::from_chars.
# Reuse the upstream Mac C-locale fallback on Android API 31 as well.
# This modifies only the ignored SDK clone in build/deps, not the submodule.
python3 "$root/scripts/patch_android_float_from_chars.py" --sdk "$sdk" --root "$root"
python3 "$root/scripts/patch_android_float_from_chars.py" --sdk "$sdk" --root "$root" --check
# NDK r27 libc++ lacks std::jthread/stop_token; keep original host code.
python3 "$root/scripts/patch_android_timer_thread.py" --sdk "$sdk" --root "$root"
python3 "$root/scripts/patch_android_timer_thread.py" --sdk "$sdk" --root "$root" --check
# FABLE2_MEMEXPORT62_SDK_AUDIT: diagnostic instrumentation only.
# Does not certify global guest exclusion or enable MemExport commits.
python3 "$root/scripts/patch_rex_memexport62.py" --sdk "$sdk" --root "$root"
python3 "$root/scripts/patch_rex_memexport62.py" --sdk "$sdk" --root "$root" --check \
  --report "$root/build/rexglue-memexport62-instrumentation.json"
memgate71_mode="${FABLE2_MEMGATE71_DIAGNOSTIC:-0}"
if [[ "$memgate71_mode" != "0" && "$memgate71_mode" != "1" ]]; then
  echo 'BLOCKED: invalid Memgate71 runtime mode' >&2; exit 2
fi
if [[ "$memgate71_mode" == "1" ]]; then
  if ! python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$sdk" --check >/dev/null 2>&1; then
    python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$sdk"
  fi
  python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$sdk" --check
fi
python3 "$root/scripts/audit_android_sdk.py" --sdk "$sdk" \
  --json "$root/build/rexglue-android-sdk-audit.json"
# ABI59: libfable2.so needs real rex::perf::GetSnapshotCounter.
# ReXGlue builds perf/counter.cpp only when this option is ON.
build="$root/build/rexglue-android-arm64"
cmake -S "$sdk" -B "$build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 -DANDROID_STL=c++_shared \
  -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_ENABLE_PERF_COUNTERS=ON \
  -DREXGLUE_ARM64_MARCH=armv8-a \
  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \
  '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384' \
  -DFABLE2_MEMGATE71_DIAGNOSTIC="$memgate71_mode" \
  -DFABLE2_MEMGATE71_SOURCE="$root/port/sdk/fable_memgate71.cpp" \
  -DFABLE2_MEMGATE71_INCLUDE="$root/port/sdk"
cmake --build "$build" --target rexruntime --parallel "${BUILD_JOBS:-2}"
if [[ "$memgate71_mode" == "1" ]]; then
  test -s "$build/libfable2_memgate71.so" || {
    echo 'BLOCKED: runtime Memgate71 shared DSO not produced' >&2; exit 2;
  }
fi
# Upstream CMakeList.txt deliberately emits shared libraries OUTSIDE the
# -B binary directory: ${REXGLUE_ROOT}/out/${REX_PLATFORM}/librexruntime.so.
# Package the freshly built ARM64 output with dependency closure and an ELF
# report, so CI artifact uploads do not assume a wrong path or ship host libs.
artifact="$root/build/artifacts/rexglue-android-arm64"
readelf="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
[[ -x "$readelf" ]] || {
  echo "BLOCKED: missing NDK llvm-readelf: $readelf" >&2; exit 2;
}
python3 "$root/scripts/package_rexruntime_arm64.py" \
  --sdk-root "$sdk" --build-root "$build" --ndk-home "$ANDROID_NDK_HOME" \
  --output "$artifact" --readelf "$readelf"
[[ -s "$artifact/librexruntime.so" && -s "$artifact/runtime-build-report.json" ]] || {
  echo 'BLOCKED: verified ARM64 runtime was not staged into build/artifacts' >&2
  exit 2
}
if [[ "$memgate71_mode" == "1" ]]; then
  cp "$build/libfable2_memgate71.so" "$artifact/libfable2_memgate71.so"
fi
# # FTESTE_REXRUNTIME_16K_39: reject 4-KiB ELF PT_LOAD segments before uploading the artifact.
python3 "$root/scripts/check_android_16k_alignment.py" \
  --directory "$artifact" \
  --report "$root/build/rexruntime-arm64-alignment.json"
echo "Compiled and packaged genuine ReXGlue AArch64 runtime: $artifact/librexruntime.so"
printf 'export REXRUNTIME_LIB=%q\n' "$artifact/librexruntime.so"
printf 'export REXSDK_DIR=%q\n' "$sdk"
echo 'NOT VERIFIED: Fable II guest .so, Plume/EDRAM, audio output, saves and gameplay.'
