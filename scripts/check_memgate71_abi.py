#!/usr/bin/env python3
"""Fail-closed ARM64 DT_NEEDED/SONAME check of the opt-in Memgate71 guest DSO.

This does NOT certify coverage of uninstrumented memory writers or GPU RAM
commits. Checks library identity and ELF linkage only, never proprietary code.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SONAME = 'libfable2_memgate71.so'
REQUIRED = ('fable_memgate71_enter', 'fable_memgate71_leave',
            'fable_memgate71_acquire_diagnostic',
            'fable_memgate71_release_diagnostic',
            'fable_memgate71_snapshot', 'fable_memgate71_commit_permitted')


def elf_aarch64(path: Path) -> bool:
    with path.open('rb') as stream:
        header = stream.read(64)
    return (len(header) == 64 and header[:4] == b'\x7fELF' and
            header[4:6] == b'\x02\x01' and
            int.from_bytes(header[16:18], 'little') == 3 and
            int.from_bytes(header[18:20], 'little') == 183)


def read_dynamic(tool: str, path: Path) -> tuple[set[str], str | None]:
    output = subprocess.check_output([tool, '-d', str(path)], text=True)
    deps = set(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', output))
    names = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', output)
    if len(names) > 1:
        raise ValueError('Ambiguous ELF SONAME')
    return deps, names[0] if names else None


def inspect(guest: Path, gate: Path, readelf: str) -> dict:
    if not elf_aarch64(guest) or not elf_aarch64(gate):
        raise ValueError('Only authentic AArch64 ELF64 little-endian DSOs accepted')
    needed, _ = read_dynamic(readelf, guest)
    if SONAME not in needed:
        raise ValueError('Guest ELF does not depend on process-wide Memgate71 DSO')
    _, gate_soname = read_dynamic(readelf, gate)
    if gate_soname != SONAME or gate.name != SONAME:
        raise ValueError('Shared gate SONAME/name mismatch')
    exported = subprocess.check_output([readelf, '--dyn-syms', str(gate)], text=True)
    for symbol in REQUIRED:
        if not re.search(r'\b' + re.escape(symbol) + r'(?:@\S+)?\b', exported):
            raise ValueError('Shared gate C ABI missing: ' + symbol)
    return {
        'stage': 71,
        'status': 'LINKAGE_ONLY_NOT_CERTIFIED',
        'guest_requires_shared_gate': True,
        'gate_soname': SONAME,
        'abi_version': 1,
        'required_export_count': len(REQUIRED),
        'all_writers_certified': False,
        'gpu_guest_ram_commit_permitted': False,
        'guest_runtime_gpu_concurrency_proven': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest', required=True, type=Path)
    parser.add_argument('--gate', required=True, type=Path)
    parser.add_argument('--readelf', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.guest, args.gate, args.readelf)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('BLOCKED Memgate71 ABI: ' + str(exc), file=sys.stderr)
        return 2
    print('PASS: ARM64 guest links one shared diagnostic gate DSO')
    print('BLOCKED: GPU RAM commits and global writer coverage remain unverified')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
