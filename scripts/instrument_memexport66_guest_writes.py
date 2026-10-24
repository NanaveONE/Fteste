#!/usr/bin/env python3
"""Opt-in MemExport66 diagnostic C++ writer instrumentation, private only.

Transforms the *generated C++* from a verified private ZIP and can install it
only into an ignored build worktree. Never modifies the original ZIP, tracked
sources, or guest RAM. No stop-the-world guarantee or MemExport certification.

The stage-65 inventory is reconciled against every transformed call. New or
unparsed call forms fail closed rather than being silently skipped.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from zipfile import ZipFile, BadZipFile

from audit_memexport63_guest_writes import MAX_FILES, MAX_BYTES, SOURCE
from classify_memexport65_guest_access import (ATOMIC_CALL, MEMORY_CALL, GUEST_HINT,
                                                balanced, classify_body, mask_non_code,
                                                split_args)

INCLUDE = '#include "fable_memexport_writer66.h"\n'
HEADER = Path(__file__).resolve().parents[1] / 'port/sdk/fable_memexport_writer66.h'
MARKER = 'FABLE2_MEMEXPORT66_OBSERVER'
ATOMIC_READ = re.compile(r'^__atomic_load')
ATOMIC_FENCE = {'__sync_synchronize', '__atomic_thread_fence', '__atomic_signal_fence'}
MAX_MEMBERS = MAX_FILES + 200


class Blocked(ValueError):
    pass


def spans_for_source(source: str) -> tuple[list[tuple[int, int, str]], dict]:
    """Return validated expression call spans with no overlapping replacements."""
    masked = mask_non_code(source)
    counts = classify_body(source.encode('latin1'))
    spans: list[tuple[int, int, str]] = []
    for regex, group in ((ATOMIC_CALL, 'Atomic'), (MEMORY_CALL, 'MemoryIntrinsic')):
        for match in regex.finditer(masked):
            name = match.group(1)
            if group == 'Atomic' and (name in ATOMIC_FENCE or ATOMIC_READ.match(name)):
                continue
            beginning = match.start()
            line_start = masked.rfind('\n', 0, beginning) + 1
            # Do not rewrite a preprocessor directive or macro definition.
            if masked[line_start:beginning].lstrip().startswith('#'):
                raise Blocked('Writer call in preprocessor directive; review required')
            open_paren = masked.find('(', match.start(), match.end() + 2)
            parsed = balanced(masked, open_paren, '(', ')')
            if parsed is None:
                raise Blocked('Unbalanced writer call; refuse partial instrumentation')
            arguments, end = parsed
            if group == 'Atomic':
                args = split_args(arguments)
                if not args or not GUEST_HINT.search(args[0]):
                    # We still cannot assume a non-REX pointer is harmless.
                    raise Blocked('Unknown atomic destination; classify first')
            spans.append((beginning, end, group))
    spans.sort()
    for previous, current in zip(spans, spans[1:]):
        if previous[1] > current[0]:
            raise Blocked('Nested/overlapping writer calls; requires syntax-aware rewrite')
    actual = Counter(kind for _start, _end, kind in spans)
    if (actual['Atomic'] != counts.get('atomic_potential_write_calls', 0)
            or actual['MemoryIntrinsic'] != counts.get('memory_intrinsic_calls', 0)
            or counts.get('atomic_unparsed_calls', 0)
            or counts.get('memory_intrinsic_unparsed_calls', 0)
            or counts.get('atomic_address_unknown_write_candidates', 0)):
        raise Blocked('MemExport65 inventory and rewrite candidates differ')
    # Detect known direct dereference writes that are not wrapped. This stage
    # targets call expressions only; direct stores still require an analysis.
    return spans, counts


def transform(source: bytes) -> tuple[bytes, dict[str, int]]:
    if MARKER.encode() in source or INCLUDE.encode() in source:
        raise Blocked('Duplicate or partial MemExport66 installation')
    # Latin-1 preserves byte offsets even for arbitrary UTF-8 comments.
    code = source.decode('latin1')
    spans, classification = spans_for_source(code)
    result = code
    for start, end, kind in reversed(spans):
        original = result[start:end]
        result = (result[:start] +
                  f'fable2::memexport66::ObserveWrite(fable2::memexport66::Kind::{kind}, '
                  f'[&]() -> decltype(auto) {{ return {original}; }})' + result[end:])
    if spans:
        result = INCLUDE + '// ' + MARKER + ': diagnostic-only call observation.\n' + result
    counts = {
        'atomic_calls_wrapped': sum(k == 'Atomic' for _, _, k in spans),
        'memory_intrinsics_wrapped': sum(k == 'MemoryIntrinsic' for _, _, k in spans),
        'direct_guest_store_candidates_uncovered': classification.get('direct_guest_write_candidates', 0),
        'raw_address_references_total_unclassified': classification.get('rex_raw_addr_calls', 0),
    }
    return result.encode('latin1'), counts


def _read_archive(archive: Path) -> tuple[list[tuple[str, bytes]], str]:
    with ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise Blocked('Private ZIP has too many members')
        matches = [i for i in infos if SOURCE.search(i.filename)]
        if not matches or len(matches) > MAX_FILES or len({i.filename for i in matches}) != len(matches):
            raise Blocked('Missing/duplicated private C++ files')
        if any(i.file_size > MAX_BYTES for i in matches) or sum(i.file_size for i in matches) > MAX_BYTES:
            raise Blocked('Private source bytes exceed limit')
        # Same provenance scheme as 63/65, independent of ZIP entry order.
        sources = []
        hashes = []
        for info in matches:
            if not re.fullmatch(r'fable_2_(?:recomp\.\d+|init|register)\.cpp', Path(info.filename).name):
                raise Blocked('Invalid C++ basename')
            data = z.read(info)
            sources.append((Path(info.filename).name, data))
            hashes.append(hashlib.sha256(data).hexdigest())
    if len({name for name, _ in sources}) != len(sources):
        raise Blocked('Duplicate generated basename')
    digest = hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest()
    return sources, digest


def prepare(archive: Path, output_dir: Path, report_path: Path,
            expect_source_hash: str | None = None,
            expect_atomics: int | None = None,
            expect_intrinsics: int | None = None) -> dict:
    archive = archive.resolve(strict=True)
    output_dir = output_dir.resolve()
    report_path = report_path.resolve()
    if not output_dir.is_relative_to(Path.cwd().resolve() / 'build'):
        raise Blocked('Output must stay under the ignored build/ directory')
    if report_path.is_relative_to(output_dir) or output_dir.exists():
        raise Blocked('Output exists or report overlaps output; refusing overwrite')
    if not HEADER.is_file():
        raise Blocked('MemExport66 header missing')
    source_list, source_hash = _read_archive(archive)
    if expect_source_hash and source_hash.lower() != expect_source_hash.lower():
        raise Blocked('Unexpected private generated source-set hash')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.memexport66-', dir=output_dir.parent))
    counts: Counter[str] = Counter()
    out_hashes = []
    try:
        for basename, original in source_list:
            new, summary = transform(original)
            counts.update(summary)
            target = staged / basename
            target.write_bytes(new)
            out_hashes.append(hashlib.sha256(new).hexdigest())
        if expect_atomics is not None and counts['atomic_calls_wrapped'] != expect_atomics:
            raise Blocked(f'Atomic count drift: {counts["atomic_calls_wrapped"]} != expected {expect_atomics}')
        if expect_intrinsics is not None and counts['memory_intrinsics_wrapped'] != expect_intrinsics:
            raise Blocked(f'Memory intrinsic drift: {counts["memory_intrinsics_wrapped"]} != expected {expect_intrinsics}')
        shutil.copyfile(HEADER, staged / HEADER.name)
        report = {
            'stage': 66,
            'status': 'GUEST_WRITER_TELEMETRY_ONLY_NOT_CERTIFIED',
            'translation_units': len(source_list),
            'original_source_set_sha256': source_hash,
            'instrumented_source_set_sha256': hashlib.sha256(''.join(sorted(out_hashes)).encode()).hexdigest(),
            'counters': dict(sorted(counts.items())),
            'all_writer_paths_covered': False,
            'global_exclusion_certified': False,
            'memexport_commit_permitted': False,
            'warning': 'This is NOT a memory lock. Other guest/host writes, caches and DMA are not certified.',
        }
        (staged / 'memexport66-report.json').write_text(json.dumps(report, indent=2) + '\n')
        # Rename staging directory only after every source was transformed.
        staged.replace(output_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--expected-source-sha256')
    p.add_argument('--expected-atomics', type=int)
    p.add_argument('--expected-intrinsics', type=int)
    args = p.parse_args()
    try:
        report = prepare(args.archive, args.output_dir, args.report,
                         args.expected_source_sha256, args.expected_atomics,
                         args.expected_intrinsics)
    except (OSError, Blocked, BadZipFile, ValueError) as error:
        print(f'BLOCKED MemExport66: {error}', file=sys.stderr)
        return 2
    print('PASS: private MemExport66 instrumented guest sources created under build/')
    print('BLOCKED: global CPU/GPU guest memory synchronization still NOT proven')
    print(json.dumps({'files': report['translation_units'], 'counts': report['counters']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
