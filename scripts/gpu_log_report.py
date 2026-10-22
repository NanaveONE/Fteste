#!/usr/bin/env python3
"""Summarize observable Xerenge Plume graphics problems from a Fable II run.

Does not guess GPU compatibility from shader-cache size. Use with device logs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

PATTERNS = {
    'missing_shader': re.compile(r'(?:cache\s*MISS|shader[^\n]*not\s+found|no\s+.*shader|FABLE2_MISSING_PIPELINE|draw pipeline skipped)', re.I),
    'missing_pipeline': re.compile(r'(?:FABLE2_MISSING_PIPELINE|pipeline[^\n]*(?:fail|missing|reject|skipped)|no\s+pipeline)', re.I),
    'missing_feature': re.compile(r'(?:unsupported|not\s+supported|missing\s+feature)', re.I),
    'gpu_error': re.compile(r'(?:VK_ERROR_|Vulkan[^\n]*error|createShader\s+failed|EDRAM[^\n]*fail)', re.I),
    'rejected_draw': re.compile(r'(?:ring\s+rejected|draw[^\n]*reject|reject[^\n]*draw)', re.I),
}
HASHES = re.compile(r'\b(?:0x)?[0-9a-fA-F]{16}\b')
PIPELINE = re.compile(r'(?:FABLE2_MISSING_PIPELINE|draw pipeline skipped)\s+vs=([0-9a-fA-F]{16})\s+\((ok|miss)\)\s+ps=([0-9a-fA-F]{16})\s+\((ok|miss)\)', re.I)
COVERAGE = re.compile(r'shader coverage\s*[-:]\s*VS\s+(\d+)/(\d+)\s+distinct,\s*PS\s+(\d+)/(\d+)\s+distinct,\s*draws with both\s+(\d+)/(\d+)', re.I)


def summarize(lines: list[str]) -> dict:
    counts: Counter[str] = Counter()
    hashes: dict[str, Counter[str]] = {}
    examples: dict[str, str] = {}
    missing_vs: set[str] = set()
    missing_ps: set[str] = set()
    missing_pairs: set[tuple[str, str]] = set()
    last_coverage: dict | None = None
    for line in lines:
        if 'plume:' not in line.lower() and 'rexgpu' not in line.lower() and 'vulkan' not in line.lower():
            continue
        matched_pipeline = PIPELINE.search(line)
        if matched_pipeline:
            vs, vs_status, ps, ps_status = matched_pipeline.groups()
            if vs_status.lower() == 'miss':
                missing_vs.add(vs.lower())
            if ps_status.lower() == 'miss':
                missing_ps.add(ps.lower())
            missing_pairs.add((vs.lower(), ps.lower()))
        matched_coverage = COVERAGE.search(line)
        if matched_coverage:
            vs_found, vs_all, ps_found, ps_all, draws_with_shaders, draws_all = map(int, matched_coverage.groups())
            last_coverage = {
                'vs_found': vs_found, 'vs_observed': vs_all,
                'ps_found': ps_found, 'ps_observed': ps_all,
                'draws_with_both_shaders': draws_with_shaders, 'draws_observed': draws_all,
            }
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                counts[kind] += 1
                examples.setdefault(kind, line.rstrip()[:280])
                for key in HASHES.findall(line):
                    hashes.setdefault(kind, Counter())[key.lower().removeprefix('0x')] += 1
    return {
        'gpu_issue_counts': dict(counts),
        'shader_or_pipeline_hashes': {key: dict(items.most_common(25)) for key, items in hashes.items()},
        'examples': examples,
        'distinct_missing_vertex_shaders': sorted(missing_vs),
        'distinct_missing_pixel_shaders': sorted(missing_ps),
        'distinct_skipped_pipeline_pairs': len(missing_pairs),
        'last_shader_coverage': last_coverage,
        'warning': 'Diagnostic counts only; zero errors does not mean working graphics.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logfile', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.logfile.is_file():
        parser.error(f'Log file not found: {args.logfile}')
    summary = summarize(args.logfile.read_text(encoding='utf-8', errors='replace').splitlines())
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
