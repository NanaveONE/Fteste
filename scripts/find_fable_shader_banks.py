#!/usr/bin/env python3
"""Locate legitimate Fable II SBK shader banks with case-insensitive names.

The Xenia virtual filesystem supports case-insensitive paths, whereas Linux
and Android don't. Only search the known data/shaders folder, not arbitrary
subdirectories or unrelated SBK files.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BANKS = ('shadersrelease.sbk', 'shaders.sbk')


def locate(game_root: Path) -> list[Path]:
    game_root = game_root.expanduser().resolve()
    data = game_root / 'data'
    if not data.is_dir():
        raise ValueError('Fable II data/ folder is missing')
    matches = [path for path in data.iterdir()
               if path.is_dir() and path.name.casefold() == 'shaders']
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one data/shaders folder; found {len(matches)}')
    shader_dir = matches[0]
    found: dict[str, Path] = {}
    for p in shader_dir.iterdir():
        folded = p.name.casefold()
        if folded in BANKS and p.is_file():
            if folded in found:
                raise ValueError(f'Duplicate case-insensitive shader-bank name {p.name}')
            found[folded] = p
    if not found:
        raise ValueError('Missing Shaders.sbk / ShadersRelease.sbk in data/shaders')
    return [found[name] for name in BANKS if name in found]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game-root', type=Path, required=True)
    ap.add_argument('--print0', action='store_true', help='NUL-delimited paths for bash mapfile -d')
    a = ap.parse_args()
    try:
        paths = locate(a.game_root)
    except (ValueError, OSError) as exc:
        ap.exit(2, f'BLOCKED: {exc}\n')
    if a.print0:
        sys.stdout.buffer.write(b''.join(str(path).encode('utf-8') + b'\0' for path in paths))
    else:
        for path in paths:
            print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
