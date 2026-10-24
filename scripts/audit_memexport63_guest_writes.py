#!/usr/bin/env python3
"""Conservative inventory of direct guest memory accesses in private generated C++.

This is NOT a stop-the-world implementation and does NOT authorize MemExport.
The report contains no source excerpts, addresses or proprietary filenames.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

SOURCE = re.compile(r'(?:^|/)fable_2_(?:recomp\.\d+|init|register)\.cpp$')
PATTERNS = {
    'membase_references': re.compile(rb'\b(?:membase|physical_membase)\b'),
    'guest_store_helpers': re.compile(rb'\b(?:PPC_STORE|PPC_STORE_U|PPC_STORE_BE|STORE_U\d+|store_be|store_and_swap)\b', re.I),
    'raw_pointer_casts': re.compile(rb'\b(?:reinterpret_cast|static_cast)\s*<[^>]*\*'),
    'memory_intrinsics': re.compile(rb'\b(?:memcpy|memmove|memset|std::copy|std::fill)\s*\('),
    'atomic_operations': re.compile(rb'\b(?:atomic_ref|__atomic_store|__sync_lock_test_and_set|std::atomic)\b'),
}
MAX_FILES = 1000
MAX_BYTES = 1024 * 1024 * 1024


def inspect(files):
    files = list(files)
    if not files or len(files) > MAX_FILES:
        raise ValueError('Missing or excessive private generated translation units')
    counts = {k: 0 for k in PATTERNS}
    total = 0
    hashes = []
    for name, body in files:
        if not SOURCE.search(name) or len(body) > MAX_BYTES:
            raise ValueError('Unexpected private source entry')
        total += len(body)
        if total > MAX_BYTES:
            raise ValueError('Generated C++ exceeds audit size limit')
        hashes.append(hashlib.sha256(body).hexdigest())
        for key, pattern in PATTERNS.items():
            counts[key] += len(pattern.findall(body))
    if total == 0:
        raise ValueError('Empty generated C++')
    return {
        'stage': 63,
        'status': 'AUDIT_ONLY_NOT_CERTIFIED',
        'translation_units': len(files),
        'total_bytes': total,
        'source_set_sha256': hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest(),
        'potential_access_counts': counts,
        'direct_guest_stores_fully_instrumented': False,
        'all_writers_cooperating': False,
        'global_exclusion_certified': False,
        'memexport_commit_permitted': False,
        'warning': 'Heuristic scan only; a zero count does not prove absence of writes.',
    }


def read_sources(directory=None, archive=None):
    if bool(directory) == bool(archive):
        raise ValueError('Supply exactly one private source directory or archive')
    if directory:
        root = Path(directory)
        return [(p.name, p.read_bytes()) for p in sorted(root.glob('fable_2_*.cpp')) if SOURCE.search(p.name)]
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES + 200:
            raise ValueError('Archive contains excessive entries')
        names = [i for i in infos if SOURCE.search(i.filename)]
        if any(i.file_size > MAX_BYTES for i in names) or sum(i.file_size for i in names) > MAX_BYTES:
            raise ValueError('Archive generated C++ too large')
        if len(set(i.filename for i in names)) != len(names):
            raise ValueError('Duplicate generated C++ entries')
        return [(i.filename, z.read(i)) for i in names]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-dir', type=Path)
    group.add_argument('--archive', type=Path)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    try:
        result = inspect(read_sources(args.source_dir, args.archive))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
        print('PASS: private guest memory access inventory created locally')
        print('BLOCKED: direct writers not fully instrumented; MemExport remains disabled')
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print('BLOCKED MemExport63: ' + str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
