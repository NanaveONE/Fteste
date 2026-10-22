#!/usr/bin/env bash
# Collect on-device startup logs after installing the actual game APK.
# Does not claim that the game is playable based on process survival.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
: "${ADB:-adb}"
command -v "$ADB" >/dev/null || { echo 'BLOCKED: adb not installed' >&2; exit 2; }
package='com.nanaveone.fable2'
out="${FABLE2_DEVICE_LOG_DIR:-$root/build/device-smoke}"
mkdir -p "$out"
"$ADB" get-state | grep -qx device || { echo 'BLOCKED: Android device not authorized over ADB' >&2; exit 2; }
# This only launches the *installer* Activity, which will ask the user to
# select their own game folder if they have not imported their files.
"$ADB" shell am start -n "$package/.Fable2LauncherActivity" | tee "$out/launch.txt"
echo 'Use the app UI to import private game files, then tap Iniciar Fable II.'
echo 'If you have already imported the game, launch it now, then press Enter here.'
if [[ "${FABLE2_DEVICE_NONINTERACTIVE:-0}" != 1 ]]; then
  read -r -p 'Press Enter to collect diagnostic logs once the game was launched: ' _
fi
"$ADB" shell pidof "$package" > "$out/pid.txt" || true
"$ADB" logcat -d -v threadtime -t 2500 > "$out/logcat.txt"
"$ADB" shell dumpsys activity activities > "$out/activities.txt"
if grep -Eqi 'FATAL EXCEPTION|Fatal signal|SIGSEGV|SIGABRT|UnsatisfiedLinkError|dlopen failed|librexgpu-plume.*not found' "$out/logcat.txt"; then
  echo 'WARNING: possible native/Java crash or linker failure detected.'
  grep -Ein 'FATAL EXCEPTION|Fatal signal|SIGSEGV|SIGABRT|UnsatisfiedLinkError|dlopen failed|librexgpu-plume.*not found' "$out/logcat.txt" | tail -30
else
  echo 'No known fatal signature found in the last 2500 logcat lines (NOT proof of gameplay).'
fi
[[ -s "$out/pid.txt" ]] && echo 'App process detected at collection time.' || echo 'App process not running at collection time.'
echo "Diagnostic logs: $out"
echo 'Logs may include local device information. Inspect/redact before sharing.'
