#!/usr/bin/env python3
"""Fail-closed source audit of a ReXGlue SDK selected for Fable II on Android.

The Android fork must provide SDL_main and Android-specific runtime support.
This checks *sources*, not ABI correctness or a successful native build. Never
accept a Windows-only SDK simply because GPU headers have equal ABI numbers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED_FILES = {
    'include/rex/main_android.h': ('InitializeAndroidApp',),
    'include/rex/ui/windowed_app.h': ('REX_DEFINE_APP',),
    'include/rex/system/gpu_plugin.h': ('kGpuPluginAbiVersion', 'rex_gpu_create'),
    'src/core/main_android.cpp': ('InitializeAndroidApp',),
    'src/core/fiber_android.cpp': (),
    'src/core/filesystem_posix.cpp': ('__ANDROID__', 'GetExecutableFolder'),
    'src/ui/surface_android.cpp': (),
    'src/ui/windowed_app_main_sdl.cpp': ('SDL_main', 'REX_PLATFORM_ANDROID'),
}


def source_audit(sdk: Path, fable_sdk: Path | None = None) -> dict:
    sdk = sdk.resolve()
    report: dict = {
        'sdk_path': str(sdk), 'ready_for_source_build': False,
        'missing': [], 'errors': [], 'warnings': [], 'files': {},
    }
    for name, anchors in REQUIRED_FILES.items():
        file = sdk / name
        if not file.is_file():
            report['missing'].append(name)
            continue
        data = file.read_bytes()
        content = data.decode('utf-8', errors='replace')
        report['files'][name] = hashlib.sha256(data).hexdigest()
        for anchor in anchors:
            if anchor not in content:
                report['errors'].append(f'{name}: missing {anchor}')
    entrypoint = sdk / 'src/ui/windowed_app_main_sdl.cpp'
    if entrypoint.is_file():
        content = entrypoint.read_text(encoding='utf-8', errors='replace')
        if not re.search(r'\bSDL_main\s*\(', content):
            report['errors'].append('No SDL_main function for SDLActivity to invoke')
    gpu_api = sdk / 'include/rex/system/gpu_plugin.h'
    if gpu_api.is_file():
        content = gpu_api.read_text(encoding='utf-8', errors='replace')
        match = re.search(r'kGpuPluginAbiVersion\s*=\s*(\d+)', content)
        if match:
            report['gpu_plugin_abi'] = int(match.group(1))
        else:
            report['errors'].append('Cannot determine GPU plugin ABI version')
    if fable_sdk is not None:
        other = fable_sdk / 'include/rex/system/gpu_plugin.h'
        if other.is_file():
            content = other.read_text(encoding='utf-8', errors='replace')
            match = re.search(r'kGpuPluginAbiVersion\s*=\s*(\d+)', content)
            report['fable_original_gpu_plugin_abi'] = int(match.group(1)) if match else None
            if match and report.get('gpu_plugin_abi') != int(match.group(1)):
                report['errors'].append('Fable original and Android GPU plugin ABI version differ')
        else:
            report['warnings'].append('Cannot compare original Fable SDK: source submodule not checked out')
    report['ready_for_source_build'] = not report['missing'] and not report['errors']
    report['warnings'].append(
        'Source check only. Source-compatible ABI, C++ linkage, codegen and GPU behaviour still require real builds/tests.')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--fable-sdk', type=Path)
    parser.add_argument('--json', type=Path, help='Write machine-readable report locally')
    args = parser.parse_args()
    report = source_audit(args.sdk, args.fable_sdk)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for name in report['missing']:
        print('BLOCKED: SDK source file missing: ' + name)
    for error in report['errors']:
        print('BLOCKED: ' + error)
    for warning in report['warnings']:
        print('NOTE: ' + warning)
    if not report['ready_for_source_build']:
        return 2
    print(f'OK: Android-specific ReXGlue SDK sources present (GPU plugin ABI={report["gpu_plugin_abi"]}).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
