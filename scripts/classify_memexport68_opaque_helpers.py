#!/usr/bin/env python3
"""MemExport68: private-only helper-context hints for stage-67 opaque REX_RAW_ADDR.

No guest code is modified. Hint names are NOT evidence that a memory access is
safe, a write, or synchronized. Reports contain aggregates and provenance only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from classify_memexport65_guest_access import RAW_ADDR, balanced, mask_non_code
from classify_memexport67_raw_addresses import (
    CLASSES, classify_body as classify67_body,
    direct_deref_class, read_inputs, source_calls,
)

# Only known *name families*, never emit a private helper identifier.
HELPER = re.compile(r'\b((?:PPC|REX)_[A-Za-z0-9_]+|__builtin_[A-Za-z0-9_]+)\s*\(')
HINTS = ('helper_write_name', 'helper_read_name', 'helper_address_name',
         'helper_other_name', 'address_value_expression', 'unknown_expression')


def opaque_hints(body: bytes) -> Counter:
    code = mask_non_code(body.decode('latin1'))
    calls = sorted(source_calls(code), key=lambda item: (item[0], -item[1]))
    active = []
    scan = 0
    result = Counter()
    for m in RAW_ADDR.finditer(code):
        while scan < len(calls) and calls[scan][0] <= m.start():
            active.append(calls[scan]); scan += 1
        active = [c for c in active if c[1] > m.start()]
        # Match stage 67's treatment of unparsed invocations exactly.
        call_open = code.rfind('(', m.start(), m.end() + 1)
        if call_open < m.start() or balanced(code, call_open, '(', ')') is None:
            continue
        if any(c[0] < m.start() < c[1] for c in active):
            continue
        if direct_deref_class(code, m.start()) is not None:
            continue
        # These are hints only; an unknown prefix is never assumed to be a read.
        prefix = code[max(0, m.start() - 220):m.start()]
        line_start = max(prefix.rfind('\n'), prefix.rfind(';'),
                         prefix.rfind('{'), prefix.rfind('}')) + 1
        prefix = prefix[line_start:]
        helpers = [h.group(1) for h in HELPER.finditer(prefix) if h.group(1) != 'REX_RAW_ADDR']
        if helpers:
            helper = helpers[-1].upper()
            if re.search(r'(?:STORE|WRITE|SAVE|SETMEM)', helper):
                key = 'helper_write_name'
            elif re.search(r'(?:LOAD|READ|FETCH)', helper):
                key = 'helper_read_name'
            elif re.search(r'(?:ADDR|PTR|ADDRESS)', helper):
                key = 'helper_address_name'
            else:
                key = 'helper_other_name'
        elif re.search(r'(?<![=!<>])=(?!=)\s*$', prefix):
            key = 'address_value_expression'
        else:
            key = 'unknown_expression'
        result[key] += 1
    return result


def classify(files):
    # Read each translation unit once to avoid retaining ~300 MB of private C++
    # in a Termux Python process.
    import hashlib
    prior_counts = Counter()
    hint_counts = Counter()
    hashes = []
    total_bytes = 0
    seen = set()
    from audit_memexport63_guest_writes import MAX_FILES, MAX_BYTES, SOURCE
    for name, body in files:
        if not SOURCE.search(name) or name in seen:
            raise ValueError('Invalid or duplicate C++ source')
        seen.add(name)
        if len(seen) > MAX_FILES:
            raise ValueError('Too many private C++ sources')
        total_bytes += len(body)
        if total_bytes > MAX_BYTES:
            raise ValueError('Private C++ exceeds size limit')
        hashes.append(hashlib.sha256(body).hexdigest())
        prior_counts.update(classify67_body(body))
        hint_counts.update(opaque_hints(body))
    if not seen or not total_bytes:
        raise ValueError('No generated C++ supplied')
    raw = prior_counts['raw_address_references_total']
    if raw != sum(prior_counts[k] for k in CLASSES):
        raise ValueError('MemExport67 raw-address reconciliation failed')
    opaque = prior_counts['opaque_or_other_address_usage']
    if sum(hint_counts.values()) != opaque:
        raise ValueError(f'Opaque-context reconciliation failed: {sum(hint_counts.values())} != {opaque}')
    for key in HINTS:
        hint_counts.setdefault(key, 0)
    return {
        'stage': 68,
        'status': 'LEXICAL_HINTS_ONLY_NOT_CERTIFIED',
        'translation_units': len(seen),
        'source_set_sha256': hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest(),
        'raw_address_references': raw,
        'previously_classified_as_opaque': opaque,
        'opaque_context_hints': dict(sorted(hint_counts.items())),
        'direct_guest_stores_fully_instrumented': False,
        'all_writers_cooperating': False,
        'global_exclusion_certified': False,
        'memexport_commit_permitted': False,
        'warning': 'Lexical hints are NOT proven memory reads/writes. The generated source is unchanged. DMA and all-writer coverage remain unverified.',
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--archive', type=Path)
    g.add_argument('--source-dir', type=Path)
    ap.add_argument('--report', required=True, type=Path)
    ap.add_argument('--expected-source-sha256')
    ap.add_argument('--expected-raw-references', type=int)
    ap.add_argument('--expected-opaque-references', type=int)
    a = ap.parse_args()
    try:
        report = classify(read_inputs(archive=a.archive, source_dir=a.source_dir))
        if a.expected_source_sha256 and report['source_set_sha256'] != a.expected_source_sha256.lower():
            raise ValueError('Source provenance mismatch')
        if a.expected_raw_references is not None and report['raw_address_references'] != a.expected_raw_references:
            raise ValueError('Raw address count mismatch')
        if a.expected_opaque_references is not None and report['previously_classified_as_opaque'] != a.expected_opaque_references:
            raise ValueError('Opaque reference count mismatch')
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, AssertionError) as e:
        print('BLOCKED MemExport68: ' + str(e), file=sys.stderr)
        return 2
    print('PASS: MemExport68 private opaque helper hints generated')
    print('BLOCKED: no synchronization/certification; GPU guest RAM commit still disabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
