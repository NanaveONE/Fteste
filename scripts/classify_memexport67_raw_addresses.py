#!/usr/bin/env python3
"""MemExport67: disjoint, conservative REX_RAW_ADDR occurrence inventory.

Reads the generated Fable II C++ only from the user's private filesystem or ZIP.
The JSON is aggregated evidence, not a guest writer proof. No source text,
addresses, paths, or snippets are emitted, and nothing is instrumented here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile, BadZipFile

from audit_memexport63_guest_writes import MAX_FILES, MAX_BYTES, SOURCE
from classify_memexport65_guest_access import (
    ATOMIC_CALL, MEMORY_CALL, CAST_START, RAW_ADDR, balanced, mask_non_code,
)

# An occurrence belongs to exactly ONE category. A category labelled candidate
# is not a proof of a particular executed store, or of exclusion/synchronization.
CLASSES = (
    'atomic_first_argument_write_candidate',
    'atomic_other_argument_unknown',
    'memory_intrinsic_destination_write_candidate',
    'memory_intrinsic_source_read_candidate',
    'memory_intrinsic_other_argument_unknown',
    'direct_dereference_write_candidate',
    'direct_dereference_read_candidate',
    'opaque_or_other_address_usage',
    'unparsed_raw_address_call',
)
FENCE = {'__sync_synchronize', '__atomic_thread_fence', '__atomic_signal_fence'}
ATOMIC_LOAD = re.compile(r'^__atomic_load')
WRITE_AFTER = re.compile(r'\s*(?:(?<![=!<>])=(?!=)|\+=|-=|\*=|/=|%=|&=|\|=|\^=|\+\+|--)')
POINTER_CAST = re.compile(r'\b(?:reinterpret_cast|static_cast)\s*<')


def arg_ranges(code: str, first: int, last: int) -> list[tuple[int, int]]:
    """Top-level comma separated argument offsets, respecting nested syntax.

    The range includes whitespace; angle brackets are treated as opaque because
    '<' can also be an operator. Unknown template-heavy expressions are left
    ambiguous, rather than used to grant write permission.
    """
    ranges = []
    begin = first
    expected = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    for i in range(first, last):
        c = code[i]
        if c in pairs:
            expected.append(pairs[c])
        elif expected and c == expected[-1]:
            expected.pop()
        elif c == ',' and not expected:
            ranges.append((begin, i))
            begin = i + 1
    ranges.append((begin, last))
    return ranges


def source_calls(masked: str):
    """Return only recognized primitive call spans and argument offset ranges."""
    spans = []
    for kind, pattern in (('atomic', ATOMIC_CALL), ('memory', MEMORY_CALL)):
        for m in pattern.finditer(masked):
            op = masked.rfind('(', m.start(), m.end() + 2)
            if op < m.start():
                continue
            parsed = balanced(masked, op, '(', ')')
            if parsed is None:
                # Report these as unknown contexts rather than interpreting them.
                continue
            end = parsed[1]
            spans.append((m.start(), end, kind, m.group(1), arg_ranges(masked, op + 1, end - 1)))
    return spans


def direct_deref_class(masked: str, raw_start: int) -> str | None:
    """Check simple `*cast<T*>(REX_RAW_ADDR(...))` lvalues or rvalues.

    Does not try to infer aliases, indexing, pointer arithmetic, references,
    or general C++ semantics. Those remain opaque until a real parser proves it.
    """
    # Cast just before REX_RAW_ADDR, with no call/statement nesting mismatch.
    for match in reversed(list(POINTER_CAST.finditer(masked[max(0, raw_start - 200):raw_start]))):
        cast_start = max(0, raw_start - 200) + match.start()
        lt = max(0, raw_start - 200) + match.end() - 1
        parsed_type = balanced(masked, lt, '<', '>')
        if parsed_type is None or '*' not in parsed_type[0]:
            continue
        pos = parsed_type[1]
        while pos < len(masked) and masked[pos].isspace():
            pos += 1
        expr = balanced(masked, pos, '(', ')')
        if expr is None or not (pos < raw_start < expr[1]):
            continue
        # Recognize immediately dereferenced casts, never all casts.
        prefix = masked[max(0, cast_start - 6):cast_start]
        if not re.search(r'\*\s*$', prefix):
            continue
        after = masked[expr[1]:expr[1]+30]
        if WRITE_AFTER.match(after):
            return 'direct_dereference_write_candidate'
        return 'direct_dereference_read_candidate'
    return None


def classify_body(body: bytes) -> dict[str, int]:
    masked = mask_non_code(body.decode('latin1'))  # byte positions stable
    counts: Counter[str] = Counter()
    spans = sorted(source_calls(masked), key=lambda s: (s[0], -s[1]))
    active = []
    scan_index = 0
    raw_count = 0
    for m in RAW_ADDR.finditer(masked):
        raw_count += 1
        # Sweep spans instead of rechecking every atomic call for each raw
        # address. This matters for the 78,160 references in the real ZIP.
        while scan_index < len(spans) and spans[scan_index][0] <= m.start():
            active.append(spans[scan_index])
            scan_index += 1
        active = [call for call in active if call[1] > m.start()]
        pos = masked.rfind('(', m.start(), m.end() + 1)
        expr = balanced(masked, pos, '(', ')') if pos >= m.start() else None
        if expr is None:
            counts['unparsed_raw_address_call'] += 1
            continue
        call_start = m.start()
        containers = [call for call in active if call[0] < call_start < call[1]]
        # Outermost known side-effect operation matters: the first arg of CAS
        # contains an inner reinterpret_cast, which is not itself a store.
        if containers:
            containers.sort(key=lambda x: (x[0], -x[1]))
            _, _, kind, name, ranges = containers[0]
            arg_index = next((i for i, (begin, end) in enumerate(ranges)
                              if begin <= call_start < end), -1)
            if kind == 'atomic':
                if name in FENCE or ATOMIC_LOAD.match(name):
                    counts['atomic_other_argument_unknown'] += 1
                elif arg_index == 0:
                    counts['atomic_first_argument_write_candidate'] += 1
                else:
                    counts['atomic_other_argument_unknown'] += 1
            else:
                # memcpy/memmove/memset destination arg0;
                # std::copy destination arg2, std::fill writes to its range.
                compact = name.replace(' ', '')
                if compact == 'std::copy':
                    dest = {2}
                    source = {0, 1}
                elif compact == 'std::fill':
                    dest = {0, 1}
                    source = set()
                else:
                    dest = {0}
                    source = {1} if compact in ('memcpy', 'memmove') else set()
                if arg_index in dest:
                    counts['memory_intrinsic_destination_write_candidate'] += 1
                elif arg_index in source:
                    counts['memory_intrinsic_source_read_candidate'] += 1
                else:
                    counts['memory_intrinsic_other_argument_unknown'] += 1
            continue
        simple_deref = direct_deref_class(masked, call_start)
        counts[simple_deref or 'opaque_or_other_address_usage'] += 1
    for key in CLASSES:
        counts.setdefault(key, 0)
    counts['raw_address_references_total'] = raw_count
    assert sum(counts[k] for k in CLASSES) == counts['raw_address_references_total']
    return dict(counts)


def read_inputs(*, archive: Path | None = None, source_dir: Path | None = None):
    if (archive is None) == (source_dir is None):
        raise ValueError('Provide exactly one source directory or private ZIP')
    if archive is not None:
        with ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) > MAX_FILES + 200:
                raise ValueError('Unexpected private archive entry count')
            matches = [i for i in infos if SOURCE.search(i.filename)]
            if not matches or len(matches) > MAX_FILES or len({i.filename for i in matches}) != len(matches):
                raise ValueError('Missing/duplicate private guest C++ sources')
            if any(i.file_size > MAX_BYTES for i in matches) or sum(i.file_size for i in matches) > MAX_BYTES:
                raise ValueError('Private source bytes exceed validation limit')
            basenames = [Path(i.filename).name for i in matches]
            if len(set(basenames)) != len(basenames):
                raise ValueError('Repeated private C++ basename')
            for info in matches:
                yield info.filename, z.read(info)
    else:
        paths = sorted(p for p in source_dir.glob('fable_2_*.cpp') if SOURCE.search(p.name))
        if not paths or len(paths) > MAX_FILES:
            raise ValueError('Missing/excessive private guest C++ sources')
        for path in paths:
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Private source bytes exceed validation limit')
            yield path.name, path.read_bytes()


def classify_sources(files) -> dict:
    counts: Counter[str] = Counter()
    hashes = []
    total_bytes = 0
    seen = set()
    for name, body in files:
        if not SOURCE.search(name) or name in seen:
            raise ValueError('Invalid/duplicate private guest C++ source')
        seen.add(name)
        total_bytes += len(body)
        if total_bytes > MAX_BYTES:
            raise ValueError('Private source bytes exceed validation limit')
        hashes.append(hashlib.sha256(body).hexdigest())
        counts.update(classify_body(body))
    if not seen or len(seen) > MAX_FILES or total_bytes == 0:
        raise ValueError('Missing/excessive/empty private guest C++ source set')
    raw = counts['raw_address_references_total']
    if raw != sum(counts[k] for k in CLASSES):
        raise ValueError('Raw-address category reconciliation failed')
    return {
        'stage': 67,
        'status': 'RAW_ADDRESS_CLASSIFICATION_ONLY_NOT_CERTIFIED',
        'translation_units': len(seen),
        'total_bytes': total_bytes,
        'source_set_sha256': hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest(),
        'classification_counts': dict(sorted(counts.items())),
        'all_writers_cooperating': False,
        'global_exclusion_certified': False,
        'memexport_commit_permitted': False,
        'warning': ('Occurrences are NOT distinct write sites or proven read/write semantics. '
                    'Opaque access remains, direct CPU stores and DMA are not synchronized. '
                    'No private source excerpts included.'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--source-dir', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-source-sha256')
    parser.add_argument('--expected-raw-references', type=int)
    args = parser.parse_args()
    try:
        report = classify_sources(read_inputs(archive=args.archive, source_dir=args.source_dir))
        if args.expected_source_sha256 and report['source_set_sha256'] != args.expected_source_sha256.lower():
            raise ValueError('Private source-set hash drift')
        actual = report['classification_counts']['raw_address_references_total']
        if args.expected_raw_references is not None and actual != args.expected_raw_references:
            raise ValueError(f'Raw address count drift ({actual} vs expected {args.expected_raw_references})')
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, AssertionError, BadZipFile) as error:
        print('BLOCKED MemExport67: ' + str(error), file=sys.stderr)
        return 2
    print('PASS: private raw-address context classification completed')
    print('BLOCKED: remaining writers/DMA and guest GPU commit still unverified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
