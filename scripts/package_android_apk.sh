#!/usr/bin/env bash
# Package a REAL Android Fable II native build. This script cannot manufacture
# game code or convert Burnout's renderer into the Fable II renderer.
# Usage: ANDROID_HOME=/path/to/sdk ANDROID_NDK_HOME=/path/to/ndk \
#        SDL_JAVA_DIR=/path/to/sdl3/android-project/app/src/main/java \
#        NATIVE_LIB_DIR=/path/to/fable/arm64/libs bash scripts/package_android_apk.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
sdk="${ANDROID_HOME:?Set ANDROID_HOME to Android SDK}" 
ndk="${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME to Android NDK}"
sdl_java="${SDL_JAVA_DIR:?Set SDL_JAVA_DIR to SDL3 Android Java sources}"
libdir="${NATIVE_LIB_DIR:?Set NATIVE_LIB_DIR to native arm64 shared libraries}"
[[ -d "$sdl_java" && -d "$libdir" ]] || { echo 'Missing SDL Java sources or native libraries' >&2; exit 1; }

require_command() { command -v "$1" >/dev/null || { echo "Missing tool: $1" >&2; exit 1; }; }
for tool in javac jar keytool zip find sort; do require_command "$tool"; done

# A usable game APK must contain genuine Fable guest code, runtime and a GPU
# plugin ported for Fable II. Never produce an empty/placeholder APK.
for lib in libfable2.so librexruntime.so libc++_shared.so librexgpu-plume.so; do
  [[ -s "$libdir/$lib" ]] || { echo "BLOCKED: Missing $libdir/$lib. Do not package a fake gameplay APK." >&2; exit 2; }
done

mapfile -t build_tools < <(find "$sdk/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V)
mapfile -t platforms < <(find "$sdk/platforms" -mindepth 1 -maxdepth 1 -type d | sort -V)
[[ ${#build_tools[@]} -gt 0 && ${#platforms[@]} -gt 0 ]] || { echo 'Android SDK build tools/platform not installed' >&2; exit 1; }
tools="${build_tools[-1]}"
android_jar="${platforms[-1]}/android.jar"
[[ -s "$android_jar" ]] || { echo 'android.jar missing' >&2; exit 1; }
for command in aapt2 d8 zipalign apksigner; do
  [[ -x "$tools/$command" ]] || { echo "Missing $tools/$command" >&2; exit 1; }
done

# Reject wrong architecture before signing. This is not a gameplay test.
readelf="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
[[ -x "$readelf" ]] || { echo "Missing NDK tool $readelf" >&2; exit 1; }
for lib in libfable2.so librexruntime.so libc++_shared.so librexgpu-plume.so; do
  "$readelf" -h "$libdir/$lib" | grep -q 'Machine:.*AArch64' || {
    echo "BLOCKED: $lib is not AArch64" >&2; exit 2;
  }
done

# Check the GPU plugin's required ReXGlue exported ABI entrypoints, and reject
# accidental Burnout dependencies before creating/signing the Android package.
python3 "$root/scripts/check_native_libs.py" "$libdir" --readelf "$readelf"

out="${OUTPUT_DIR:-$root/build/fable2-apk}"
[[ "$out" != / && "$out" != "$root" ]] || { echo 'Unsafe OUTPUT_DIR' >&2; exit 1; }
mkdir -p "$out"
out="$(cd "$out" && pwd)"
rm -rf "$out/intermediates"
mkdir -p "$out/intermediates/classes" "$out/intermediates/dex" "$out/intermediates/payload/lib/arm64-v8a"

"$tools/aapt2" link --manifest "$root/port/android/AndroidManifest.xml" -I "$android_jar" \
  --min-sdk-version 31 --target-sdk-version 32 -o "$out/intermediates/base.apk"

find "$sdl_java" "$root/port/android/java" -type f -name '*.java' -print > "$out/intermediates/java_sources.txt"
[[ -s "$out/intermediates/java_sources.txt" ]] || { echo 'No Java files found' >&2; exit 1; }
javac --release 17 -encoding UTF-8 -classpath "$android_jar" \
  -d "$out/intermediates/classes" @"$out/intermediates/java_sources.txt"

# A single classes.jar avoids long argv lists for d8.
jar --create --file "$out/intermediates/classes.jar" -C "$out/intermediates/classes" .
"$tools/d8" --release --min-api 31 --lib "$android_jar" \
  --output "$out/intermediates/dex" "$out/intermediates/classes.jar"

cp "$out/intermediates/dex/classes.dex" "$out/intermediates/payload/classes.dex"
cp "$libdir"/*.so "$out/intermediates/payload/lib/arm64-v8a/"
cp "$out/intermediates/base.apk" "$out/intermediates/unaligned.apk"
(cd "$out/intermediates/payload" && zip -q -r "$out/intermediates/unaligned.apk" classes.dex lib)
"$tools/zipalign" -f 4 "$out/intermediates/unaligned.apk" "$out/intermediates/aligned.apk"

keystore="${ANDROID_KEYSTORE:-$HOME/.android/fable2-debug.keystore}"
if [[ ! -f "$keystore" ]]; then
  mkdir -p "$(dirname "$keystore")"
  keytool -genkeypair -keystore "$keystore" -storepass android -keypass android \
    -alias fable2 -keyalg RSA -keysize 2048 -validity 10000 \
    -dname 'CN=Fable II Android development' >/dev/null
fi
"$tools/apksigner" sign --ks "$keystore" --ks-key-alias fable2 \
  --ks-pass pass:android --key-pass pass:android \
  --out "$out/fable2-arm64.apk" "$out/intermediates/aligned.apk"
"$tools/apksigner" verify "$out/fable2-arm64.apk"
echo "PACKAGED: $out/fable2-arm64.apk"
echo 'WARNING: APK signature verification does NOT prove Fable II starts or renders.'
