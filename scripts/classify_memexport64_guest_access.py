#!/usr/bin/env python3
"""Conservative classification of generated C++ pointer accesses; never certifies MemExport."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_memexport63_guest_writes import read_sources, inspect

CAST = re.compile(rb'\b(?:reinterpret_cast|static_cast)\s*<[^>]*\*[^>]*>')
ASSIGN = re.compile(rb'(?<![=!<>])(?:\+=|-=|\*=|/=|%=|\|=|&=|\^=|(?<![+\-*/%|&^])=(?!=))')
INCREMENT = re.compile(rb'(?:\+\+|--)')
READ = re.compile(rb'\b(?:const|volatile)\b')
MEM_WRITE = re.compile(rb'\b(?:memcpy|memmove|memset|std::copy|std::fill)\s*\(')
MAX_EXAMPLES_PER_FILE = 0  # Never export proprietary snippets.


def classify(files):
    files = list(files)
    base = inspect(files)
    totals = {'cast_occurrences': 0, 'candidate_write_contexts': 0,
              'candidate_read_or_declaration_contexts': 0,
              'ambiguous_cast_contexts': 0, 'memory_intrinsic_calls': 0}
    for _, body in files:
        for match in CAST.finditer(body):
            totals['cast_occurrences'] += 1
            # Context classification is heuristic; statements can span multiple lines.
            # A cast on the LHS of assignment is a candidate write, not a proven guest store.
            tail = body[match.end():match.end() + 180]
            before = body[max(0, match.start()-120):match.start()]
            end = re.search(rb'[;\n]', tail)
            fragment = tail[:end.start()] if end else tail
            if ASSIGN.search(fragment) or INCREMENT.search(fragment):
                totals['candidate_write_contexts'] += 1
            elif READ.search(before) or re.search(rb'\b(?:return|if|while)\b', before[-32:]):
                totals['candidate_read_or_declaration_contexts'] += 1
            else:
                totals['ambiguous_cast_contexts'] += 1
        totals['memory_intrinsic_calls'] += len(MEM_WRITE.findall(body))
    assert sum(totals[k] for k in ('candidate_write_contexts', 'candidate_read_or_declaration_contexts', 'ambiguous_cast_contexts')) == totals['cast_occurrences']
    return {'stage': 64, 'status': 'CLASSIFICATION_ONLY_NOT_CERTIFIED',
            'translation_units': base['translation_units'],
            'source_set_sha256': base['source_set_sha256'],
            'heuristic_counts': totals,
            'direct_guest_stores_fully_instrumented': False,
            'all_writers_cooperating': False,
            'global_exclusion_certified': False,
            'memexport_commit_permitted': False,
            'warning': 'Heuristic classification: counts do not prove reads, writes, or synchronization. No private source included.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-dir', type=Path)
    group.add_argument('--archive', type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = classify(read_sources(args.source_dir, args.archive))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
        print('PASS: MemExport64 heuristic classification created locally')
        print('BLOCKED: no guest-write certification; MemExport remains disabled')
        return 0
    except (OSError, ValueError, AssertionError) as exc:
        print('BLOCKED MemExport64: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
