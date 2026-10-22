#!/usr/bin/env python3
"""Compare selected GPU interface contracts from two local ReXGlue SDK trees.

Same ABI version is necessary but NOT sufficient: runtime and renderer still
need to be built from matching source revisions and tested together.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

HEADERS = (
    'include/rex/system/gpu_plugin.h',
    'include/rex/system/interfaces/graphics.h',
)


def abi_version(content: str) -> str | None:
    found = re.search(r'kGpuPluginAbiVersion\s*=\s*(\d+)\s*;', content)
    return found.group(1) if found else None


def compare(a: Path, b: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in HEADERS:
        lhs, rhs = a / relative, b / relative
        if not lhs.is_file() or not rhs.is_file():
            errors.append('Missing SDK interface header: ' + relative)
            continue
        left = lhs.read_bytes()
        right = rhs.read_bytes()
        if relative.endswith('gpu_plugin.h'):
            left_abi = abi_version(left.decode('utf-8'))
            right_abi = abi_version(right.decode('utf-8'))
            if not left_abi or not right_abi:
                errors.append('Could not determine GPU plugin ABI version in one SDK')
            elif left_abi != right_abi:
                errors.append(f'Incompatible GPU ABI versions: {left_abi} != {right_abi}')
            else:
                print(f'OK: both GPU plugin interfaces declare ABI {left_abi}')
        if left != right:
            a_hash = hashlib.sha256(left).hexdigest()[:12]
            b_hash = hashlib.sha256(right).hexdigest()[:12]
            warnings.append(f'{relative} differs ({a_hash} != {b_hash}); manually reconcile API changes')
        else:
            print('OK: identical interface header ' + relative)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fable_sdk', type=Path)
    parser.add_argument('xerenge_sdk', type=Path)
    args = parser.parse_args()
    errors, warnings = compare(args.fable_sdk, args.xerenge_sdk)
    for problem in errors:
        print('BLOCKED: ' + problem)
    for problem in warnings:
        print('REVIEW: ' + problem)
    print('NOT VERIFIED: binary ABI, plugin interoperability, shader correctness.')
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
