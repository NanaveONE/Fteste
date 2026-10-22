#!/usr/bin/env python3
"""Check PT_LOAD segment alignment of genuine Android ARM64 ELF libraries.

No NDK/readelf required: reads the standard ELF64 little-endian program headers.
16 KiB alignment is compatible with both 4 KiB and 16 KiB page-size devices.
This is a loader compatibility check, not a gameplay/EDRAM test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

MIN_PAGE_ALIGNMENT = 16 * 1024
ELF_HEADER_SIZE = 64
PROGRAM_HEADER_SIZE = 56
MAX_PROGRAM_HEADERS = 1024
PT_LOAD = 1


def load_alignments(path: Path) -> list[int]:
    if not path.is_file() or path.stat().st_size < ELF_HEADER_SIZE:
        raise ValueError(f'Missing/truncated ELF: {path.name}')
    with path.open('rb') as stream:
        hdr = stream.read(ELF_HEADER_SIZE)
        if hdr[:4] != b'\x7fELF' or hdr[4] != 2 or hdr[5] != 1:
            raise ValueError(f'Not ELF64 little-endian: {path.name}')
        if (struct.unpack_from('<H', hdr, 16)[0] != 3 or
                struct.unpack_from('<H', hdr, 18)[0] != 183):
            raise ValueError(f'Not an AArch64 shared object: {path.name}')
        phoff = struct.unpack_from('<Q', hdr, 32)[0]
        phentsize = struct.unpack_from('<H', hdr, 54)[0]
        phnum = struct.unpack_from('<H', hdr, 56)[0]
        if not (0 < phnum <= MAX_PROGRAM_HEADERS and
                phentsize >= PROGRAM_HEADER_SIZE and
                phoff >= ELF_HEADER_SIZE and
                phoff + phnum * phentsize <= path.stat().st_size):
            raise ValueError(f'Invalid ELF program-header directory: {path.name}')
        result: list[int] = []
        for i in range(phnum):
            stream.seek(phoff + i * phentsize)
            ph = stream.read(PROGRAM_HEADER_SIZE)
            p_type = struct.unpack_from('<I', ph, 0)[0]
            if p_type != PT_LOAD:
                continue
            p_offset, p_vaddr = struct.unpack_from('<QQ', ph, 8)
            p_align = struct.unpack_from('<Q', ph, 48)[0]
            if p_align == 0 or p_align & (p_align - 1):
                raise ValueError(f'Invalid PT_LOAD segment p_align: {path.name}')
            if p_offset % p_align != p_vaddr % p_align:
                raise ValueError(f'Incongruent ELF segment offset/virtual address: {path.name}')
            result.append(p_align)
    if not result:
        raise ValueError(f'No PT_LOAD segments: {path.name}')
    return result


def audit(paths: list[Path], *, minimum: int = MIN_PAGE_ALIGNMENT) -> dict:
    if minimum <= 0 or minimum & (minimum - 1):
        raise ValueError('Minimum ELF page alignment must be power of two')
    if not paths:
        raise ValueError('No native libraries to inspect')
    records = {}
    for file in paths:
        if file.name in records:
            raise ValueError(f'Duplicate native shared-object name: {file.name}')
        aligns = load_alignments(file)
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                digest.update(block)
        records[file.name] = {
            'bytes': file.stat().st_size, 'sha256': digest.hexdigest(),
            'load_segments': len(aligns), 'minimum_pt_load_alignment': min(aligns),
            'aligned_16kb': all(a >= minimum for a in aligns),
        }
    mismatched = sorted(name for name, r in records.items() if not r['aligned_16kb'])
    return {
        'state': 'PASS' if not mismatched else 'BLOCKED',
        'required_alignment': minimum,
        'libraries': records,
        'misaligned_libraries': mismatched,
        'notes': 'ELF alignment only. Does not test hard-coded 4KB memory assumptions or runtime/gameplay.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--directory', type=Path)
    group.add_argument('--file', type=Path, action='append')
    parser.add_argument('--report', type=Path, help='Optional JSON report (no game binaries)')
    args = parser.parse_args()
    try:
        paths = sorted(args.directory.glob('*.so')) if args.directory else args.file
        report = audit(paths)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.exit(2, f'BLOCKED: {error}\n')
    for name, record in report['libraries'].items():
        print(f'{"PASS" if record["aligned_16kb"] else "BLOCKED"}: '
              f'{name} PT_LOAD p_align={record["minimum_pt_load_alignment"]} bytes')
    if report['misaligned_libraries']:
        print('Recompile with Android NDK r27 -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
