#!/usr/bin/env python3
"""MemExport65: inventory actual guest pointer / atomic forms in private C++.

Diagnostic only. Does not rewrite code, verify complete coverage, or authorize
MemExport commits. Output never includes source excerpts, paths, or addresses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from audit_memexport63_guest_writes import inspect, read_sources

# We mask comments and strings to avoid reporting examples rather than code.
COMMENT_STRING = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
CAST_START = re.compile(r'\b(static_cast|reinterpret_cast|const_cast|dynamic_cast)\s*<')
RAW_ADDR = re.compile(r'\bREX_RAW_ADDR\s*\(')
ATOMIC_CALL = re.compile(r'\b(__sync_[A-Za-z0-9_]+|__atomic_[A-Za-z0-9_]+)\s*\(')
MEMORY_CALL = re.compile(r'\b(memcpy|memmove|memset|std\s*::\s*(?:copy|fill))\s*\(')
DIRECT_DEREF = re.compile(r'\*\s*$')
ASSIGN_AFTER = re.compile(r'\s*(?:=(?!=)|\+=|-=|\*=|/=|\|=|&=|\^=|%=|\+\+|--)')
NUMERIC = re.compile(r'(?:std::)?(?:int\d+_t|uint\d+_t|size_t|ptrdiff_t)|(?:signed|unsigned|short|long|char|int|float|double|bool)(?:\s+(?:signed|unsigned|short|long|char|int|float|double|bool))*')
GUEST_HINT = re.compile(r'\b(?:REX_RAW_ADDR|physical_membase|virtual_membase)\b')


def mask_non_code(src: str) -> str:
    def blank(m: re.Match) -> str:
        return re.sub(r'[^\n]', ' ', m.group())
    return COMMENT_STRING.sub(blank, src)


def balanced(text: str, start: int, opener: str, closer: str):
    """Return (interior, end-position) for balanced delimiters; fail closed."""
    if start >= len(text) or text[start] != opener:
        return None
    depth = 0
    for at in range(start, len(text)):
        ch = text[at]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1:at], at + 1
    return None


def split_args(src: str) -> list[str]:
    result, start = [], 0
    stack: list[str] = []
    close = {'(': ')', '[': ']', '{': '}'}
    for at, ch in enumerate(src):
        if ch in close:
            stack.append(close[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
        elif ch == ',' and not stack:
            result.append(src[start:at])
            start = at + 1
    result.append(src[start:])
    return result


def classify_body(body: bytes) -> dict[str, int]:
    source = mask_non_code(body.decode('utf-8', 'replace'))
    totals: Counter[str] = Counter()
    for m in CAST_START.finditer(source):
        kind = m.group(1)
        ty = balanced(source, m.end() - 1, '<', '>')
        if ty is None:
            totals['unparsed_cast_syntax'] += 1
            continue
        type_name, end_type = ty
        totals['cast_total'] += 1
        if '*' not in type_name and '&' not in type_name and kind == 'static_cast' and NUMERIC.fullmatch(type_name.strip()):
            totals['numeric_static_casts'] += 1
            continue
        if '*' not in type_name:
            totals['other_nonpointer_casts'] += 1
            continue
        totals['pointer_casts'] += 1
        pos = end_type
        while pos < len(source) and source[pos].isspace():
            pos += 1
        expression = balanced(source, pos, '(', ')')
        if expression is None:
            totals['unparsed_pointer_casts'] += 1
            continue
        arg, end_expr = expression
        if RAW_ADDR.search(arg):
            totals['pointer_casts_with_rex_raw_addr'] += 1
        else:
            totals['pointer_casts_without_rex_raw_addr'] += 1
        # Only *cast(ptr) = ... is an unambiguous candidate direct store.
        # Nested assignments inside arguments are NOT interpreted as stores.
        if DIRECT_DEREF.search(source[max(0, m.start()-24):m.start()]) and ASSIGN_AFTER.match(source[end_expr:end_expr + 12]):
            totals['direct_dereference_write_candidates'] += 1
            if RAW_ADDR.search(arg):
                totals['direct_guest_write_candidates'] += 1
    totals['rex_raw_addr_calls'] = len(RAW_ADDR.findall(source))
    for m in ATOMIC_CALL.finditer(source):
        kind = m.group(1)
        totals['atomic_calls_all'] += 1
        parsed = balanced(source, m.end() - 1, '(', ')')
        if parsed is None:
            totals['atomic_unparsed_calls'] += 1
            continue
        args = split_args(parsed[0])
        if kind in ('__sync_synchronize', '__atomic_thread_fence', '__atomic_signal_fence'):
            totals['atomic_fence_calls'] += 1
            continue
        if kind.startswith('__atomic_load'):
            totals['atomic_load_calls'] += 1
            continue
        totals['atomic_potential_write_calls'] += 1
        # The first pointer operand is where __sync/__atomic instructions write.
        if args and GUEST_HINT.search(args[0]):
            totals['atomic_guest_memory_write_candidates'] += 1
        else:
            totals['atomic_address_unknown_write_candidates'] += 1
        if 'compare_and_swap' in kind or 'compare_exchange' in kind:
            totals['atomic_conditional_write_candidates'] += 1
    for m in MEMORY_CALL.finditer(source):
        totals['memory_intrinsic_calls'] += 1
        parsed = balanced(source, m.end() - 1, '(', ')')
        if parsed is None:
            totals['memory_intrinsic_unparsed_calls'] += 1
            continue
        args = split_args(parsed[0])
        # For std::copy the destination is the third argument.
        dest_idx = 2 if 'copy' in m.group(1) and 'std' in m.group(1) else 0
        if len(args) > dest_idx and GUEST_HINT.search(args[dest_idx]):
            totals['memory_intrinsic_guest_destination_candidates'] += 1
        else:
            totals['memory_intrinsic_other_destinations'] += 1
    return dict(totals)


def classify(files) -> dict:
    files = list(files)
    provenance = inspect(files)
    counts: Counter[str] = Counter()
    for _name, body in files:
        counts.update(classify_body(body))
    for k in (
        'cast_total', 'numeric_static_casts', 'other_nonpointer_casts',
        'pointer_casts', 'pointer_casts_with_rex_raw_addr',
        'pointer_casts_without_rex_raw_addr', 'direct_dereference_write_candidates',
        'direct_guest_write_candidates', 'rex_raw_addr_calls',
        'atomic_calls_all', 'atomic_potential_write_calls',
        'atomic_conditional_write_candidates', 'atomic_guest_memory_write_candidates',
        'atomic_address_unknown_write_candidates', 'memory_intrinsic_calls',
        'memory_intrinsic_guest_destination_candidates', 'unparsed_cast_syntax',
        'unparsed_pointer_casts', 'atomic_unparsed_calls',
        'memory_intrinsic_unparsed_calls', 'atomic_fence_calls',
        'atomic_load_calls', 'memory_intrinsic_other_destinations',
    ):
        counts.setdefault(k, 0)
    if counts['cast_total'] != counts['numeric_static_casts'] + counts['other_nonpointer_casts'] + counts['pointer_casts']:
        raise ValueError('Cast inventory did not reconcile')
    # The same instruction may appear in several categories; do NOT sum these
    # counts as unique stores. The only hard finding is that coverage is not proven.
    return {
        'stage': 65,
        'status': 'ATOMIC_AND_POINTER_AUDIT_ONLY_NOT_CERTIFIED',
        'translation_units': provenance['translation_units'],
        'total_bytes': provenance['total_bytes'],
        'source_set_sha256': provenance['source_set_sha256'],
        'classification_counts': dict(sorted(counts.items())),
        'direct_guest_stores_fully_instrumented': False,
        'all_writers_cooperating': False,
        'global_exclusion_certified': False,
        'memexport_commit_permitted': False,
        'warning': 'Atomic writes can be conditional. Pointer casts alone do not prove access. '
                   'This is heuristic evidence, NOT a complete store analysis; no guest source exposed.',
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-dir', type=Path)
    group.add_argument('--archive', type=Path)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    try:
        report = classify(read_sources(a.source_dir, a.archive))
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, AssertionError) as e:
        print('BLOCKED MemExport65: ' + str(e), file=sys.stderr)
        return 2
    print('PASS: MemExport65 classified numerical casts, pointers, atomics and memcpy destinations')
    print('BLOCKED: full writer coverage not proven; no GPU guest-RAM commits enabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
