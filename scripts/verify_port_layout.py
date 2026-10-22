#!/usr/bin/env python3
"""Verify our actual upstream-to-Android integration points, not APK readiness."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
checks = {
    "Fable recomp CMake": root / "external/Fable-2-Recomp/CMakeLists.txt",
    "Fable guest manifest": root / "external/Fable-2-Recomp/fable_2_manifest.toml",
    "Fable game entry": root / "external/Fable-2-Recomp/src/main.cpp",
    "Xerenge Android CMake": root / "external/Xerenge/rexglue/CMakeLists.txt",
    "Xerenge SDLActivity": root / "external/Xerenge/rexglue/android/java/com/xerenge/burnout/BurnoutActivity.java",
    "Xerenge Vulkan renderer": root / "external/Xerenge/rexglue/src/plume_renderer",
    "Port Fable SDLActivity": root / "port/android/java/com/nanaveone/fable2/Fable2Activity.java",
    "Port AndroidManifest": root / "port/android/AndroidManifest.xml",
}
failed = False
for label, path in checks.items():
    exists = path.exists()
    print(f"{'OK' if exists else 'MISSING'}: {label}: {path.relative_to(root)}")
    failed |= not exists
if failed:
    print("Run: git submodule update --init --recursive", file=sys.stderr)
    sys.exit(1)

android_manifest = root / "port/android/AndroidManifest.xml"
ET.parse(android_manifest)
fable_main = checks["Fable game entry"].read_text(encoding="utf-8")
xerenge_cmake = checks["Xerenge Android CMake"].read_text(encoding="utf-8")
assert "REX_DEFINE_APP(fable_2" in fable_main, "Fable entrypoint changed"
assert "elseif(ANDROID)" in xerenge_cmake or "if(ANDROID)" in xerenge_cmake, "Xerenge Android setup changed"
print("OK: upstream Fable entrypoint and Xerenge Android target patterns checked")
print("NOT READY: native runtime/render backend/guest codegen are not integrated. No APK produced.")
