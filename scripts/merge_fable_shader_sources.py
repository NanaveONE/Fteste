#!/usr/bin/env python3
"""Combine static and captured Fable II HLSL metadata without silent hash collisions.

The Xerenge shader-source-info host generator accepts one directory. Both
shader caches must be represented in its table for vertex attribute layouts,
texture bindings and constants to be resolved from the same set of sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

STEM = re.compile(r'[0-9a-fA-F]{16}\.hlsl$')


def read_dir(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise ValueError(f'Missing HLSL directory: {directory}')
    result = {}
    for file in directory.glob('*.hlsl'):
        if not STEM.fullmatch(file.name):
            raise ValueError(f'Unexpected HLSL filename: {file.name}')
        name = file.name.upper()
        if name in result and file.read_bytes() != result[name].read_bytes():
            raise ValueError(f'Conflicting HLSL hash in {directory}: {file.name}')
        result[name] = file
    return result


def merge(static: Path, runtime: Path, output: Path) -> dict:
    a, b = read_dir(static), read_dir(runtime)
    for key in set(a) & set(b):
        if a[key].read_bytes() != b[key].read_bytes():
            raise ValueError(f'Fable shaders share hash but disagree: {key}')
    chosen = dict(a)
    chosen.update(b)
    if output.exists():
        raise ValueError('Merged HLSL output exists: inspect before rebuilding')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.fable-hlsl-') as tmp:
        folder = Path(tmp)
        for name, source in chosen.items():
            shutil.copy2(source, folder / name)
        # The result directory is kept when the temporary manager closes.
        folder.rename(output)
    report = {'static_hlsl': len(a), 'runtime_hlsl': len(b), 'merged_hlsl': len(chosen)}
    (output / 'merge-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--static', required=True, type=Path)
    p.add_argument('--runtime', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        report = merge(a.static, a.runtime, a.output)
    except (OSError, ValueError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    print('Combined shader sources for GPU metadata:', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
