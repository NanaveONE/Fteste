#!/usr/bin/env python3
"""Inspect compiled Android ELF dependencies and exported GPU plugin ABI.

This is a pre-packaging compatibility gate, NOT proof of rendering/gameplay.
Use the llvm-readelf from the Android NDK for cross-architecture ELF binaries.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REQUIRED = ("libfable2.so", "librexruntime.so", "libc++_shared.so", "librexgpu-plume.so")
UNWANTED = ("libburnout.so", "libmain_eu.so", "libmain_us.so", "libxerenge_installer.so")
GPU_SYMBOLS = ("rex_gpu_abi_version", "rex_gpu_create")


def run_readelf(program: str, flag: str, path: Path) -> str:
    call = subprocess.run((program, flag, str(path)), text=True, capture_output=True, check=False)
    if call.returncode != 0:
        raise ValueError(f"Unable to inspect {path.name}: {call.stderr.strip()}")
    return call.stdout


def parse_needed(text: str) -> set[str]:
    return set(re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", text))


def check(directory: Path, readelf: str) -> list[str]:
    errors: list[str] = []
    for old in UNWANTED:
        if (directory / old).exists():
            errors.append(f"Unrelated Burnout library must not be packaged: {old}")
    for lib in REQUIRED:
        path = directory / lib
        if not path.is_file() or path.stat().st_size < 100:
            errors.append(f"Missing or truncated library: {lib}")
            continue
        try:
            header = run_readelf(readelf, '-h', path)
            dynamic = run_readelf(readelf, '-d', path)
        except ValueError as ex:
            errors.append(str(ex))
            continue
        if not re.search(r'Machine:\s*AArch64', header):
            errors.append(f"{lib}: not an AArch64 Android binary")
        dependencies = parse_needed(dynamic)
        for old in UNWANTED:
            if old in dependencies:
                errors.append(f"{lib}: contains unrelated Burnout/Xerenge dependency {old}")
        if lib == 'librexgpu-plume.so':
            try:
                symbols = run_readelf(readelf, '--dyn-syms', path)
            except ValueError as ex:
                errors.append(str(ex))
                continue
            for symbol in GPU_SYMBOLS:
                if not re.search(r'\b' + re.escape(symbol) + r'(?:@\S+)?\b', symbols):
                    errors.append(f"{lib}: GPU plugin entry point not exported: {symbol}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_lib_dir', type=Path)
    parser.add_argument('--readelf', default='llvm-readelf')
    args = parser.parse_args()
    failures = check(args.native_lib_dir, args.readelf)
    for message in failures:
        print('BLOCKED: ' + message)
    if failures:
        return 2
    print('OK: Android ELF architecture, DT_NEEDED and GPU ABI symbol checks passed.')
    print('NOT VERIFIED: plugin host ABI version match, shaders, game rendering, gameplay.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
