#!/usr/bin/env python3
"""Find the REAL ReXGlue ARM64 output and stage its DT_NEEDED closure.

ReXGlue sets CMAKE_LIBRARY_OUTPUT_DIRECTORY to sdk/out/android-arm64, even
when configured via cmake -B <separate-dir>. A successful Ninja link is not a
valid artifact unless the ELF and every non-system dependency are collected.

No game binaries or XEX/SBK content are ever read by this script.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SYSTEM_ANDROID = frozenset({
    'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libandroid.so',
    'libvulkan.so', 'libEGL.so', 'libGLESv1_CM.so', 'libGLESv2.so',
    'libGLESv3.so', 'libOpenSLES.so', 'libaaudio.so', 'libz.so',
    'libjnigraphics.so', 'libmediandk.so', 'libnativewindow.so',
    'libsync.so', 'libatomic.so', 'libunwind.so', 'libstdc++.so',
    'libcamera2ndk.so', 'libamidi.so', 'libbinder_ndk.so',
})
REJECTED_GAME_LIBS = frozenset({'libfable2.so', 'libburnout.so', 'libmain_us.so', 'libmain_eu.so'})


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def inspect(path: Path, readelf: str) -> dict:
    """Verify the architecture from ELF bytes (not a filename or tool text)."""
    if not path.is_file() or path.stat().st_size < 64:
        raise ValueError(f'Missing/truncated native shared object: {path}')
    with path.open('rb') as source:
        hdr = source.read(64)
    if (hdr[:4] != b'\x7fELF' or hdr[4] != 2 or hdr[5] != 1 or
            int.from_bytes(hdr[16:18], 'little') != 3 or
            int.from_bytes(hdr[18:20], 'little') != 183):
        raise ValueError(f'Not an AArch64 ELF64 little-endian shared library: {path.name}')
    command = subprocess.run((readelf, '-d', str(path)), text=True,
                             capture_output=True, check=False)
    if command.returncode:
        raise ValueError(f'llvm-readelf failed for {path.name}: {command.stderr[-500:]}')
    needed = sorted(set(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', command.stdout)))
    soname = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', command.stdout)
    if soname and soname[0] != path.name:
        raise ValueError(f'Unexpected DT_SONAME for {path.name}: {soname[0]}')
    return {'soname': soname[0] if soname else None, 'needed': needed,
            'sha256': digest(path), 'bytes': path.stat().st_size}


def find_runtime(sdk: Path, build: Path) -> Path:
    """Use CMake's output dir, then known in-build fallbacks; never whole workspace."""
    sdk, build = sdk.resolve(), build.resolve()
    configured = sdk / 'out/android-arm64/librexruntime.so'
    fallback = [build / 'librexruntime.so', build / 'src/system/librexruntime.so']
    found = [p for p in [configured, *fallback] if p.is_file()]
    if not found:
        raise ValueError(f'No librexruntime.so in configured SDK output ({configured}) or {build}')
    if len({digest(path) for path in found}) > 1:
        raise ValueError('Different runtime libraries found in SDK output vs CMake build; stale build collision')
    return configured if configured.is_file() else found[0]


def _ndk_libcxx(ndk: Path) -> Path:
    return (ndk / 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/'
                  'aarch64-linux-android/libc++_shared.so')


def _inventory(sdk: Path, build: Path, ndk: Path) -> dict[str, Path]:
    """Only scan the SAME Android checkout/build; never pick host x86 .so."""
    result: dict[str, Path] = {}
    locations = [sdk / 'out/android-arm64', build]
    for folder in locations:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*.so')):
            if path.name in REJECTED_GAME_LIBS:
                continue
            old = result.get(path.name)
            if old is not None and digest(old) != digest(path):
                raise ValueError(f'Conflicting native libraries with filename {path.name}')
            result.setdefault(path.name, path)
    libcxx = _ndk_libcxx(ndk)
    if libcxx.is_file():
        existing = result.get('libc++_shared.so')
        if existing is not None and digest(existing) != digest(libcxx):
            raise ValueError('libc++_shared.so conflicts with selected Android NDK')
        result['libc++_shared.so'] = libcxx
    return result


def prepare(sdk: Path, build: Path, ndk: Path, output: Path, readelf: str) -> dict:
    sdk, build, ndk, output = map(lambda p: p.expanduser().resolve(), (sdk, build, ndk, output))
    if output.exists():
        raise ValueError(f'Artifact directory already exists: {output}; refusing to publish stale output')
    source = find_runtime(sdk, build)
    inventory = _inventory(sdk, build, ndk)
    # Prefer precisely the .so linked by this SDK checkout, not another copy.
    inventory['librexruntime.so'] = source
    pending = deque(['librexruntime.so'])
    checked = {}
    while pending:
        name = pending.popleft()
        if name in checked or name in SYSTEM_ANDROID:
            continue
        if name in REJECTED_GAME_LIBS:
            raise ValueError(f'Unexpected commercial/game DT_NEEDED dependency: {name}')
        path = inventory.get(name)
        if path is None:
            raise ValueError(f'Unresolved ARM64 runtime DT_NEEDED: {name}. '
                             f'Check SDK/out/android-arm64 and the Android NDK libc++ runtime.')
        checked[name] = inspect(path, readelf)
        pending.extend(n for n in checked[name]['needed'] if n not in SYSTEM_ANDROID)
    if 'librexruntime.so' not in checked:
        raise ValueError('Runtime was not inspected')
    symbols = subprocess.run((readelf, '--dyn-syms', str(source)), text=True,
                             capture_output=True, check=False)
    if symbols.returncode:
        raise ValueError('Failed to inspect ReXGlue runtime exports: ' + symbols.stderr[-500:])
    sdl_main = bool(re.search(r'\bSDL_main(?:@\S+)?\b', symbols.stdout))
    # The game library can also own SDL_main; absence here is reported, not faked.
    report = {
        'kind': 'ReXGlue Android runtime ONLY',
        'status': 'ARM64_ELF_AND_DT_NEEDED_VERIFIED',
        'architecture': 'aarch64', 'android_api': 31,
        'library_count': len(checked),
        'libraries': checked, 'exports_sdl_main': sdl_main,
        'upstream_output_layout': 'sdk/out/android-arm64',
        'limits': 'Not a Fable II APK; game/Plume Vulkan/EDRAM and gameplay untested',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rexruntime-artifact-', dir=output.parent) as tmp:
        stage = Path(tmp)
        for name in sorted(checked):
            shutil.copyfile(inventory[name], stage / name)
            if digest(stage / name) != checked[name]['sha256']:
                raise ValueError(f'Copy verification failed for {name}')
        (stage / 'runtime-build-report.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        os.rename(stage, output)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root', required=True, type=Path)
    p.add_argument('--build-root', required=True, type=Path)
    p.add_argument('--ndk-home', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--readelf', required=True)
    a = p.parse_args()
    try:
        report = prepare(a.sdk_root, a.build_root, a.ndk_home, a.output, a.readelf)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    print(f'OK: staged {report["library_count"]} authentic Android arm64 ELF libraries; '
          'runtime native artifact is ready to upload.')
    print(f'NOTICE: SDL_main exported by runtime: {report["exports_sdl_main"]} '
          '(game library may also export entrypoint).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
