#!/usr/bin/env python3
"""Check Fable Xenos 0x102A11 containers against XenosRecomp's shader.h layout.

Strictly structural: does not translate shader bytecode and cannot prove DXC
supports all instructions. Reports statistics only (no copyrighted bytes).
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
try:
    from scripts.extract_fable_sbk import parse_bank
except ModuleNotFoundError:
    from extract_fable_sbk import parse_bank


def audit(paths: list[Path]) -> dict:
    containers = {}
    for path in paths:
        bank = parse_bank(path.read_bytes(), filename=path.name)
        for shader in bank.shaders:
            containers.setdefault(shader.sha256, shader)
    total = len(containers)
    stages = Counter()
    microcode = {}
    problems = Counter()
    for shader in containers.values():
        data = shader.data
        flags, virtual, physical, _fieldc, ctable, dtable, shader_offset, t1, t2 = struct.unpack_from('>9I', data)
        stages['VS' if flags & 1 else 'PS'] += 1
        if shader_offset + 24 > virtual or virtual + physical != len(data):
            problems['invalid_metadata_or_total_length'] += 1
            continue
        physical_offset, shader_size = struct.unpack_from('>2I', data, shader_offset)
        if (physical_offset + shader_size > physical or not shader_size or shader_size % 12):
            problems['invalid_xenos_microcode_bounds_or_alignment'] += 1
            continue
        code = data[virtual + physical_offset:virtual + physical_offset + shader_size]
        digest = hashlib.sha256(code).hexdigest()
        microcode.setdefault(digest, {'stage': 'VS' if flags & 1 else 'PS'})
    return {
        'containers': total,
        'vertex_shaders': stages['VS'],
        'pixel_shaders': stages['PS'],
        'distinct_microcode_sequences': len(microcode),
        'containers_reusing_microcode': total - len(microcode),
        'problems': dict(problems),
        'status': 'PASS' if total and not problems else 'BLOCKED',
        'note': 'Validated XenosRecomp shader.h bounds and 12-byte instructions, not HLSL/DXC compilation.',
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--banks', nargs='+', required=True, type=Path)
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    result = audit(args.banks)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
