#!/usr/bin/env python3
"""Audit actual prerequisites for a Fable II Android native compilation.

No assets are downloaded, redistributed or uploaded. This deliberately fails
without a compatible, user-provided default.xex and Android build environment.
A passing preflight does not prove the game will render or be playable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Mapping


def audit(root: Path, env: Mapping[str, str], *, check_host: bool = True) -> dict:
    root = root.resolve()
    failures: list[dict[str, str]] = []
    passed: list[str] = []
    warnings: list[str] = []

    def require_file(label: str, value: str | Path | None, *, executable: bool = False):
        if not value:
            failures.append({'requirement': label, 'reason': 'path not configured'})
            return
        path = Path(value).expanduser()
        if not path.is_file():
            failures.append({'requirement': label, 'reason': 'file not found'})
        elif executable and not os.access(path, os.X_OK):
            failures.append({'requirement': label, 'reason': 'not executable'})
        elif path.stat().st_size == 0:
            failures.append({'requirement': label, 'reason': 'empty file'})
        else:
            passed.append(label)

    def require_dir(label: str, value: str | Path | None):
        if not value:
            failures.append({'requirement': label, 'reason': 'path not configured'})
        elif not Path(value).expanduser().is_dir():
            failures.append({'requirement': label, 'reason': 'directory not found'})
        else:
            passed.append(label)

    if check_host:
        if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
            failures.append({'requirement': 'build host', 'reason': 'Linux x86_64 required for provided scripts'})
        else:
            passed.append('build host')
        for command in ('python3', 'cmake', 'ninja', 'git', 'clang', 'clang++', 'javac', 'java', 'keytool'):
            if shutil.which(command):
                passed.append('tool: ' + command)
            else:
                failures.append({'requirement': 'tool: ' + command, 'reason': 'command not installed'})

    require_file('Fable II recomp CMake', root / 'external/Fable-2-Recomp/CMakeLists.txt')
    require_file('Fable II recomp manifest', root / 'external/Fable-2-Recomp/fable_2_manifest.toml')
    catalog = root / 'external/Fable-2-Recomp/constants/game_versions.json'
    require_file('Fable II supported-version catalog', catalog)
    require_file('Xerenge GPU source', root / 'external/Xerenge/rexglue/src/plume_renderer/plugin_main.cpp')
    game_root = Path(env['FABLE2_GAME_ROOT']).expanduser() if env.get('FABLE2_GAME_ROOT') else None
    require_file('private game default.xex', game_root / 'default.xex' if game_root else None)
    require_dir('private game data/', game_root / 'data' if game_root else None)
    selected_profile: str | None = None
    if game_root and (game_root / 'default.xex').is_file():
        xex = game_root / 'default.xex'
        with xex.open('rb') as source:
            if source.read(4) != b'XEX2':
                failures.append({'requirement': 'private game default.xex', 'reason': 'not an XEX2 executable'})
        if catalog.is_file():
            try:
                versions = json.loads(catalog.read_text(encoding='utf-8')).get('versions', [])
                actual_sha = hashlib.sha256()
                with xex.open('rb') as source:
                    for chunk in iter(lambda: source.read(1 << 20), b''):
                        actual_sha.update(chunk)
                actual_sha = actual_sha.hexdigest().lower()
                match = next((v for v in versions if v.get('hash', '').lower() == actual_sha
                              and v.get('xexSize') == xex.stat().st_size), None)
                if match is None:
                    failures.append({'requirement': 'Fable II XEX version',
                                     'reason': 'not in compatible ReXGlue catalog (SHA-256 / size mismatch)'})
                elif not match.get('compatible', False):
                    failures.append({'requirement': 'Fable II XEX version',
                                     'reason': 'catalog profile is explicitly unsupported'})
                else:
                    selected_profile = str(match.get('id', 'unknown'))
                    passed.append('Fable II XEX version: ' + selected_profile)
                    for relative in match.get('requiredFiles', []):
                        if not (game_root / relative).is_file():
                            failures.append({'requirement': 'Fable II required content',
                                             'reason': 'missing ' + str(relative)})
                    for relative in match.get('rejectFiles', []):
                        if (game_root / relative).exists():
                            failures.append({'requirement': 'Fable II mixed/TU1 content',
                                             'reason': 'unexpected ' + str(relative)})
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                failures.append({'requirement': 'Fable II version catalog',
                                 'reason': 'invalid catalog structure'})
    ndk = Path(env['ANDROID_NDK_HOME']).expanduser() if env.get('ANDROID_NDK_HOME') else None
    require_file('NDK toolchain', ndk / 'build/cmake/android.toolchain.cmake' if ndk else None)
    require_file('NDK ARM64 libc++', ndk / 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so' if ndk else None)
    require_file('NDK llvm-readelf', ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf' if ndk else None, executable=True)
    sdk = Path(env['REXSDK_DIR']).expanduser() if env.get('REXSDK_DIR') else root / 'build/deps/rexglue-xerenge'
    require_file('Android ReXGlue main', sdk / 'src/core/main_android.cpp')
    require_file('Android SDL entry point', sdk / 'src/ui/windowed_app_main_sdl.cpp')
    require_file('ReXGlue GPU ABI header', sdk / 'include/rex/system/gpu_plugin.h')
    require_file('host ReXGlue code generator', env.get('FABLE2_CODEGEN_TOOL'), executable=True)
    plume = Path(env['PLUME_ROOT']).expanduser() if env.get('PLUME_ROOT') else root / 'build/deps/plume-xerenge'
    require_file('Plume CMake', plume / 'CMakeLists.txt')
    xenos = Path(env['XENOS_RECOMP_ROOT']).expanduser() if env.get('XENOS_RECOMP_ROOT') else root / 'build/deps/XenosRecomp-xerenge'
    require_file('XenosRecomp shader header', xenos / 'XenosRecomp/shader_common.h')
    require_file('XenosRecomp translator', env.get('FABLE2_SHADER_TRANSLATOR'), executable=True)
    require_file('Xerenge XEX host tool', env.get('FABLE2_XEX_DUMPER'), executable=True)
    sdk_home = Path(env['ANDROID_HOME']).expanduser() if env.get('ANDROID_HOME') else None
    require_dir('Android SDK build-tools/', sdk_home / 'build-tools' if sdk_home else None)
    require_dir('Android SDK platforms/', sdk_home / 'platforms' if sdk_home else None)
    sdl_java = env.get('SDL_JAVA_DIR') or str(sdk / 'thirdparty/sdl3/android-project/app/src/main/java')
    require_dir('SDL3 Android Java sources', sdl_java)
    if not failures:
        warnings.append('All paths exist, but ABI compatibility, successful native compilation and gameplay remain unverified.')
    return {
        'state': 'BLOCKED' if failures else 'PREREQUISITES_PRESENT',
        'verified_game_profile': selected_profile,
        'passed_count': len(passed),
        'passed': passed,
        'failures': failures,
        'warnings': warnings,
        'privacy': 'No game files, passwords, tokens, or game data are included in report.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', type=Path, help='Optional machine-readable report path (contains no game paths)')
    parser.add_argument('--no-host-check', action='store_true', help='Skip host OS/tool checks for automated layout tests')
    args = parser.parse_args()
    result = audit(args.root, os.environ, check_host=not args.no_host_check)
    print(f"{result['state']}: {len(result['failures'])} missing prerequisites; {result['passed_count']} checks passed")
    for failure in result['failures']:
        print(f"  - {failure['requirement']}: {failure['reason']}")
    for warning in result['warnings']:
        print('  NOTE: ' + warning)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('Report: ' + str(args.json))
    return 0 if not result['failures'] else 2


if __name__ == '__main__':
    sys.exit(main())
