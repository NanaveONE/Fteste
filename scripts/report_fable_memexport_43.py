#!/usr/bin/env python3
"""Privately package real Fable II DXC memexport diagnostics.

Input log + generated shader HLSL belong only to the owner. This utility
must never upload them to a public workflow artifact or source repository.
It never masks failed shader coverage or invents working GPU semantics.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

FAILED = re.compile(r'DXC SPIR-V failed for shader ([0-9a-fA-F]{16}); skipping')
INPUT = re.compile(r'Found (\d+) raw shader containers')
OUTPUT = re.compile(r'Wrote (\d+) unique shaders \((\d+) skipped\)')
MEMEXPORT = 'FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_report(log_text: str, hlsl_dir: Path, cache: Path) -> tuple[dict, list[Path]]:
    input_match = INPUT.search(log_text)
    output_match = OUTPUT.search(log_text)
    if not input_match or not output_match:
        raise ValueError('Cannot establish exact original shader counts from DXC log')
    expected, passed, skipped = int(input_match[1]), int(output_match[1]), int(output_match[2])
    names = [m.upper() for m in FAILED.findall(log_text)]
    if (expected != 588 or skipped <= 0 or expected != passed + skipped or
            len(names) != skipped or len(set(names)) != skipped):
        raise ValueError('Shader count mismatch: refusing to hide failures or mislabel cache')
    if log_text.count(MEMEXPORT) < skipped:
        raise ValueError('Non-memexport DXC failures may be present: manual inspection needed')
    if not cache.is_file() or cache.stat().st_size < 100:
        raise ValueError('Real partial shader cache missing')
    if not hlsl_dir.is_dir():
        raise ValueError('Source HLSL folder missing')
    by_name = {p.stem.upper(): p for p in hlsl_dir.glob('*.hlsl') if re.fullmatch('[0-9a-fA-F]{16}', p.stem)}
    sources = []
    records = []
    for name in names:
        path = by_name.get(name)
        if path is not None:
            sources.append(path)
        records.append({
            'shader_hash': name,
            'hlsl_found': path is not None,
            'hlsl_sha256': digest(path) if path else None,
            'memexport_directives': path.read_text(errors='replace').count(MEMEXPORT) if path else None,
        })
    return ({
        'status': 'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED',
        'total_shaders': expected,
        'translated': passed,
        'skipped': skipped,
        'coverage_percent': round(100 * passed / expected, 2),
        'shader_failures': records,
        'requires': [
            'Xenos memory export address + data semantics in GPU translator',
            'Vulkan storage buffer and guest-memory synchronization in Plume',
            'Plume descriptor-set binding 7 for patch-42 integer constant bank',
            'Plume 1D-as-2D row texture support for experimental Fable shaders',
        ],
        'warning': 'Private diagnostic and partial cache ONLY. Not a complete GPU library or playable game.',
    }, sources)


def create(log: Path, cache: Path, hlsl_dir: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('Diagnostic ZIP already exists: do not overwrite stale data')
    log_text = log.read_text(encoding='utf-8', errors='replace')
    report, sources = make_report(log_text, hlsl_dir, cache)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'x', ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        z.writestr('diagnostic/memexport-43.json', json.dumps(report, indent=2) + '\n')
        z.write(log, 'diagnostic/translator.log')
        z.write(cache, 'partial-cache/shader_cache.cpp')
        for src in sources:
            z.write(src, 'missing-hlsl/' + src.name)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--hlsl-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        report = create(a.log, a.cache, a.hlsl_dir, a.output)
    except (ValueError, OSError, UnicodeError) as err:
        p.exit(2, f'BLOCKED: {err}\n')
    print(f'PRIVATE DIAGNOSTIC: {report["translated"]}/{report["total_shaders"]} compiled, '
          f'{report["skipped"]} shader(s) need memory-export support')
    print('Never distribute or commit this private ZIP in a public repository.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
