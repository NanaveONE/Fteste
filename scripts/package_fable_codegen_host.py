#!/usr/bin/env python3
"""Package a real Linux x86_64 ReXGlue code generator, no proprietary game inputs.

Run after `cmake --build SDK/out/build/linux-amd64 --config Release --target rexglue`.
Copy only the executable and its non-system shared libraries from THAT SDK.
Validate ELF class/architecture, dependency closure and execute `--version`.
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
import struct
import subprocess


def elf_machine(path: Path) -> tuple[int, int, int]:
    with path.open('rb') as file:
        hdr = file.read(20)
    if len(hdr) < 20 or hdr[:4] != b'\x7fELF':
        raise ValueError(f'not ELF: {path}')
    if hdr[4] != 2 or hdr[5] != 1:
        raise ValueError(f'not little-endian ELF64: {path}')
    return hdr[4], hdr[5], struct.unpack_from('<H', hdr, 18)[0]


def inspect_ldd(path: Path) -> list[Path]:
    result = subprocess.run(['ldd', str(path)], text=True, capture_output=True, check=False)
    if result.returncode != 0 or 'not found' in result.stdout:
        raise ValueError(f'Host library dependency missing for {path.name}: {result.stdout} {result.stderr}')
    result_paths = []
    for line in result.stdout.splitlines():
        m = re.search(r'=>\s*(/\S+)', line)
        if m:
            result_paths.append(Path(m.group(1)))
        elif '=>' in line and 'not found' in line:
            raise ValueError(f'Unresolved host dependency: {line}')
    return result_paths


def find_codegen(sdk: Path) -> Path:
    out = sdk / 'out'
    if not out.is_dir():
        raise ValueError('SDK out/ does not exist: build the codegen target first')
    candidates = sorted(p for p in out.rglob('rexglue') if p.is_file() and os.access(p, os.X_OK))
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one built Linux rexglue executable, found {len(candidates)}')
    return candidates[0]


def package(sdk: Path, output: Path) -> dict:
    sdk = sdk.resolve(strict=True)
    executable = find_codegen(sdk)
    if elf_machine(executable)[2] != 62:  # EM_X86_64
        raise ValueError('Host rexglue must be x86_64 ELF (not Android AArch64)')
    if output.exists():
        raise ValueError('Output exists; refusing to mix old and new binaries')
    if shutil.which('patchelf') is None:
        raise ValueError('patchelf required to make host SDK dependency paths relocatable')

    # Discover closure, not just dependencies of the main executable.
    queue = deque([executable])
    local: dict[str, Path] = {}
    checked: set[Path] = set()
    while queue:
        item = queue.popleft().resolve(strict=True)
        if item in checked:
            continue
        checked.add(item)
        if elf_machine(item)[2] != 62:
            raise ValueError(f'Wrong architecture in host dependency: {item}')
        for dep in inspect_ldd(item):
            real = dep.resolve(strict=True)
            if real.is_relative_to(sdk):
                previous = local.get(dep.name)
                if previous and previous != real:
                    raise ValueError(f'Conflicting SDK library basename: {dep.name}')
                local[dep.name] = real
                queue.append(real)

    output.mkdir(parents=True)
    staged = output / 'rexglue'
    shutil.copy2(executable, staged)
    for name, source in sorted(local.items()):
        shutil.copy2(source, output / name)
    for path in [staged, *(output / name for name in local)]:
        subprocess.run(['patchelf', '--set-rpath', '$ORIGIN', str(path)], check=True)
    # `ldd` is checked AFTER relocating SDK-owned libs. System libraries remain
    # system dependencies and must be provided by the destination Linux host.
    inspect_ldd(staged)
    subprocess.run([str(staged.resolve()), '--version'], check=True, capture_output=True, text=True)
    source_sha = subprocess.run(['git', '-C', str(sdk), 'rev-parse', 'HEAD'],
                                capture_output=True, check=True, text=True).stdout.strip()
    files = [staged, *(output / name for name in sorted(local))]
    report = {
        'kind': 'linux_x86_64_rexglue_codegen',
        'game_files_included': False,
        'sdk_git_commit': source_sha,
        'executable': staged.name,
        'files': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                  for p in files},
        'warning': 'Host codegen only: not the Android game library, Vulkan plugin or an APK.',
    }
    (output / 'codegen-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (output / 'README.txt').write_text(
        'ReXGlue host codegen (Linux x86_64). This is an open-source tool, NOT Fable II.\n'
        'Use it only with your legally extracted, local Fable II content on a Linux machine.\n'
        'Do not upload game files or generated Fable II sources to public GitHub Actions.\n',
        encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = package(args.sdk, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        parser.exit(2, f'BLOCKED: {e}\n')
    print('OK: Linux x86_64 ReXGlue host codegen packaged; files:', ', '.join(result['files']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
