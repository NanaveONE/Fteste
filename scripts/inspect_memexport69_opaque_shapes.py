#!/usr/bin/env python3
"""MemExport69: structural (not semantic) inventory of opaque REX_RAW_ADDR uses.

This tool DOES NOT establish read/write semantics or unlock MemExport. It groups
previously opaque stage-67 references by nearby C++ syntax, not helper names.
Default JSON contains aggregates only. Optional private examples are written
ONLY to a user-chosen file under the repository's ignored build/ directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_memexport63_guest_writes import MAX_BYTES, MAX_FILES, SOURCE
from classify_memexport65_guest_access import RAW_ADDR, balanced, mask_non_code
from classify_memexport67_raw_addresses import (
    CLASSES, classify_body as classify67_body, direct_deref_class,
    read_inputs, source_calls,
)

SHAPES = (
    'passed_as_unknown_call_argument',
    'pointer_cast_operand',
    'return_or_yield_expression',
    'assignment_rhs_expression',
    'address_or_pointer_arithmetic',
    'postfix_index_or_member_expression',
    'unary_address_or_dereference_expression',
    'other_expression',
)
CAST_NEAR = re.compile(r'\b(?:reinterpret_cast|static_cast|const_cast|dynamic_cast)\s*<[^>\n]{0,120}>\s*\($')
CALL_NEAR = re.compile(r'(?:\b[A-Za-z_][\w:]*\s*\(|\b[A-Za-z_][\w:]*\s*\([^;{}]*,\s*)$')
ASSIGN = re.compile(r'(?<![=!<>])=(?!=)|\+=|-=|\*=|/=|%=|&=|\|=|\^=')
RETURN = re.compile(r'\b(?:return|co_return)$')


def context_shape(code: str, start: int, end: int) -> str:
    """Identify a *syntactic neighborhood*, not whether it reads or writes."""
    statement_start = max(code.rfind(';', 0, start), code.rfind('{', 0, start),
                          code.rfind('}', 0, start)) + 1
    prefix = code[max(statement_start, start - 240):start].rstrip()
    suffix = code[end:end + 48].lstrip()
    # These are deliberately coarse buckets: helper identity remains private.
    if CAST_NEAR.search(prefix):
        return 'pointer_cast_operand'
    if CALL_NEAR.search(prefix):
        return 'passed_as_unknown_call_argument'
    if RETURN.search(prefix):
        return 'return_or_yield_expression'
    if re.search(r'(?:\+|\-|\*|/|%|<<|>>|&|\|)\s*$', prefix) or re.match(r'(?:\+|\-|\*|/|%|<<|>>|&|\|)', suffix):
        return 'address_or_pointer_arithmetic'
    if suffix.startswith(('->', '.', '[')):
        return 'postfix_index_or_member_expression'
    if re.search(r'(?:\*|&)\s*$', prefix):
        return 'unary_address_or_dereference_expression'
    if ASSIGN.search(prefix):
        return 'assignment_rhs_expression'
    return 'other_expression'


def classify_opaque_body(body: bytes, *, example_limit: int = 0):
    """Match stage 67 exclusion rules exactly, then shape-label opaque sites."""
    original = body.decode('latin1')
    code = mask_non_code(original)
    spans = sorted(source_calls(code), key=lambda s: (s[0], -s[1]))
    active = []
    cursor = 0
    counters = Counter()
    samples = defaultdict(list)
    for m in RAW_ADDR.finditer(code):
        while cursor < len(spans) and spans[cursor][0] <= m.start():
            active.append(spans[cursor])
            cursor += 1
        active = [call for call in active if call[1] > m.start()]
        op = code.rfind('(', m.start(), m.end() + 1)
        parsed = balanced(code, op, '(', ')') if op >= m.start() else None
        if parsed is None or any(c[0] < m.start() < c[1] for c in active):
            continue
        if direct_deref_class(code, m.start()) is not None:
            continue
        key = context_shape(code, m.start(), parsed[1])
        counters[key] += 1
        if example_limit and len(samples[key]) < example_limit:
            # PRIVATE only; no source snippets are placed in the JSON report.
            line_start = original.rfind('\n', 0, m.start()) + 1
            line_end = original.find('\n', m.start())
            if line_end < 0:
                line_end = len(original)
            samples[key].append(original[line_start:line_end][:300].strip())
    for key in SHAPES:
        counters.setdefault(key, 0)
    return counters, samples


def audit(files, *, example_limit: int = 0):
    if not 0 <= example_limit <= 3:
        raise ValueError('Private sample limit must be 0..3 per shape')
    total_bytes = 0
    count = 0
    hashes = []
    seen = set()
    totals = Counter()
    stage67 = Counter()
    examples = defaultdict(list)
    for name, body in files:
        basename = Path(name).name
        if not SOURCE.search(name) or basename in seen:
            raise ValueError('Invalid or repeated private C++ translation unit')
        seen.add(basename)
        count += 1
        if count > MAX_FILES:
            raise ValueError('Excessive translation units')
        total_bytes += len(body)
        if total_bytes > MAX_BYTES:
            raise ValueError('Excessive private C++ source data')
        hashes.append(hashlib.sha256(body).hexdigest())
        stage67.update(classify67_body(body))
        local, local_examples = classify_opaque_body(body, example_limit=example_limit)
        totals.update(local)
        for category, sample_lines in local_examples.items():
            left = example_limit - len(examples[category])
            if left > 0:
                examples[category].extend(sample_lines[:left])
    if not count or not total_bytes:
        raise ValueError('Missing or empty private sources')
    raw = stage67['raw_address_references_total']
    opaque = stage67['opaque_or_other_address_usage']
    if raw != sum(stage67[c] for c in CLASSES):
        raise ValueError('Stage 67 inventory mismatch')
    if opaque != sum(totals[k] for k in SHAPES):
        raise ValueError(f'Opaque reconciliation failure: {sum(totals[k] for k in SHAPES)} != {opaque}')
    report = {
        'stage': 69,
        'status': 'STRUCTURAL_CONTEXT_ONLY_NOT_CERTIFIED',
        'translation_units': count,
        'source_set_sha256': hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest(),
        'raw_address_references': raw,
        'previously_opaque_references': opaque,
        'structural_context_counts': {key: totals[key] for key in SHAPES},
        'all_writers_cooperating': False,
        'global_exclusion_certified': False,
        'memexport_commit_permitted': False,
        'warning': ('Structural groupings do NOT establish reads or writes, complete coverage, '
                    'or exclusive guest-memory access. Unknown helper semantics, DMA and host '
                    'writers remain blocking. Private source never included in this JSON.'),
    }
    return report, examples


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--source-dir', type=Path)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--expected-source-sha256')
    p.add_argument('--expected-raw-references', type=int)
    p.add_argument('--expected-opaque-references', type=int)
    p.add_argument('--private-examples', type=Path,
                   help='Optional unredacted LOCAL snippets; path MUST be inside ignored build/')
    args = p.parse_args()
    try:
        report_path = args.report.resolve()
        if args.private_examples:
            dest = args.private_examples.resolve()
            build = (Path(__file__).resolve().parents[1] / 'build').resolve()
            if not dest.is_relative_to(build) or dest == report_path:
                raise ValueError('Private examples must stay in ignored build/ and differ from report')
            if dest.exists():
                raise ValueError('Refusing to overwrite private example file')
        report, examples = audit(read_inputs(archive=args.archive, source_dir=args.source_dir),
                                 example_limit=2 if args.private_examples else 0)
        if args.expected_source_sha256 and report['source_set_sha256'] != args.expected_source_sha256.lower():
            raise ValueError('Private source hash changed')
        if args.expected_raw_references is not None and report['raw_address_references'] != args.expected_raw_references:
            raise ValueError('REX_RAW_ADDR reference count changed')
        if args.expected_opaque_references is not None and report['previously_opaque_references'] != args.expected_opaque_references:
            raise ValueError('Opaque count changed')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        if args.private_examples:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('x', encoding='utf-8') as out:
                out.write('PRIVATE: illustrative source lines; NEVER upload to public GitHub\n')
                for category in SHAPES:
                    for line in examples[category]:
                        out.write(f'{category}: {line}\n')
    except (OSError, ValueError, AssertionError) as exc:
        print(f'BLOCKED MemExport69: {exc}', file=sys.stderr)
        return 2
    print('PASS: structural context inventory reconciled against stage 67')
    print('BLOCKED: structural categories do not prove complete writers or MemExport safety')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
