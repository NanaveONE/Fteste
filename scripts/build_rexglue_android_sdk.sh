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
python3 "$root/scripts/audit_android_sdk.py" --sdk "$sdk" \
  --json "$root/build/rexglue-android-sdk-audit.json"
build="$root/build/rexglue-android-arm64"
cmake -S "$sdk" -B "$build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 -DANDROID_STL=c++_shared \
  -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_ENABLE_PERF_COUNTERS=OFF \
  -DREXGLUE_ARM64_MARCH=armv8-a
cmake --build "$build" --target rexruntime --parallel "${BUILD_JOBS:-2}"
mapfile -t libraries < <(find "$build" -type f -name librexruntime.so -print)
if [[ ${#libraries[@]} != 1 ]]; then
  echo "BLOCKED: expected one ARM64 librexruntime.so, found ${#libraries[@]}" >&2
  exit 2
fi
readelf="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
"$readelf" -h "${libraries[0]}" | grep -q 'Machine:.*AArch64' || {
  echo 'BLOCKED: ReXGlue runtime was not compiled for AArch64' >&2; exit 2;
}
echo "Android ReXGlue runtime compiled: ${libraries[0]}"
printf 'export REXRUNTIME_LIB=%q\n' "${libraries[0]}"
printf 'export REXSDK_DIR=%q\n' "$sdk"
echo 'This is a real runtime build, not proof of the Fable II guest code or GPU.'
