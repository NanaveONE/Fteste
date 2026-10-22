#!/usr/bin/env python3
"""Translate Fable II shaders captured during gameplay into a Plume cache.

This consumes Xerenge's REAL .bin / .wrapargs produced by the Fable-only
Plume graphics overlay. Unlike Burnout's --from-disc recipe, no game-specific
hardcoded shader recipe is assumed. Captures must come from the user's own
installation. Produces a Bootstrap-suffixed C++ cache understood by Plume.

Important: offline capture->translate->rebuild; NOT live JIT compilation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

NAME = re.compile(r'^(VS|PS)_([0-9A-Fa-f]{16})_([1-9][0-9]*)\.wrapargs$')
BASE_SYMBOLS = ('g_shaderCacheEntriesBootstrap', 'g_shaderCacheEntryCountBootstrap',
                'g_compressedSpirvCacheBootstrap', 'g_spirvCacheCompressedSizeBootstrap',
                'g_shaderMicrocodeEntriesBootstrap', 'g_shaderMicrocodeEntryCountBootstrap')
VALID_OPTIONS = {'VS': {'--element', '--interpolator', '--sampler'},
                 'PS': {'--interpolator', '--outputs'}}


def digest(file: Path) -> str:
    checksum = hashlib.sha256()
    with file.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def read_capture(directory: Path) -> list[tuple[str, Path, list[str]]]:
    if not directory.is_dir():
        raise ValueError(f'Capture folder missing: {directory}')
    captures = []
    for args_file in sorted(directory.glob('*.wrapargs')):
        m = NAME.fullmatch(args_file.name)
        if not m:
            raise ValueError(f'Unexpected shader capture filename: {args_file.name}')
        stage, _hash, count = m.groups()
        micro = directory / (args_file.stem + '.bin')
        if not micro.is_file() or micro.stat().st_size != int(count) or int(count) % 12:
            raise ValueError(f'Microcode missing/size invalid (needs whole 12-byte instructions): {micro.name}')
        nonempty = [x.strip() for x in args_file.read_text(encoding='utf-8').splitlines()
                    if x.strip() and not x.lstrip().startswith('#')]
        if len(nonempty) != 1:
            raise ValueError(f'Expected exactly one shader declaration: {args_file.name}')
        args = shlex.split(nonempty[0])
        if len(args) % 2 or not args:
            raise ValueError(f'Invalid option/value pairs: {args_file.name}')
        for option, value in zip(args[::2], args[1::2]):
            if option not in VALID_OPTIONS[stage] or not value or value.startswith('--'):
                raise ValueError(f'Unexpected shader declaration {option} for {stage}: {args_file.name}')
        if stage == 'VS' and '--element' not in args:
            raise ValueError(f'Vertex shader has no --element: {args_file.name}')
        captures.append((stage, micro, args))
    if not captures:
        raise ValueError('No .wrapargs shader captures present')
    return captures


def execute(binary: Path, *args: str, env: dict | None = None, optional: bool = False):
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f'Executable missing: {binary}')
    result = subprocess.run([str(binary), *map(str, args)],
                            check=False, capture_output=True, text=True, env=env)
    if result.returncode != 0 and not optional:
        raise ValueError(f'{binary.name} returned {result.returncode}: {result.stderr[-1200:]}')
    return result.returncode == 0


def compile_captures(capture_dir: Path, output: Path, guest_image: Path,
                     translator: Path, header: Path, rehost: Path,
                     wrap_vs: Path, wrap_ps: Path, rename: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise ValueError(f'Output exists; refusing to reuse stale shader data: {output}')
    for source in (guest_image, header):
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError(f'Required input missing: {source}')
    captures = read_capture(capture_dir)
    output.mkdir(parents=True)
    containers = output / 'runtime-containers'
    hlsl = output / 'xenos-hlsl'
    containers.mkdir()
    hlsl.mkdir()
    rehosted = 0
    for stage, micro, options in captures:
        dest = containers / (micro.stem + '.container')
        if execute(rehost, str(guest_image), str(micro), str(dest), optional=True) and dest.is_file() and dest.stat().st_size > 0:
            rehosted += 1
            continue
        if not execute(wrap_vs if stage == 'VS' else wrap_ps, str(micro), str(dest), *options):
            raise ValueError(f'Could not wrap shader {micro.name}')
        if not dest.is_file() or dest.stat().st_size == 0:
            raise ValueError(f'Wrapper produced no container: {micro.name}')
    raw = output / 'shader_cache_runtime_raw.cpp'
    cache = output / 'shader_cache_runtime.cpp'
    env = dict(os.environ, XENOS_RECOMP_DUMP_SOURCE_DIR=str(hlsl))
    execute(translator, str(containers), str(raw), str(header), env=env)
    if not raw.is_file() or raw.stat().st_size == 0:
        raise ValueError('XenosRecomp did not produce a shader cache')
    execute(rename, str(raw), str(cache), '--suffix', 'Bootstrap')
    if not cache.is_file() or any(symbol not in cache.read_text(encoding='utf-8', errors='replace')
                                  for symbol in BASE_SYMBOLS):
        raise ValueError('Translated cache does not export Plume Bootstrap symbols')
    report = {
        'source_title': 'Fable II runtime shader captures',
        'capture_count': len(captures),
        'rehosted_count': rehosted,
        'guest_image_sha256': digest(guest_image),
        'shader_cache_sha256': digest(cache),
        'capture_files': {p.name: digest(p) for _stage, p, _args in captures},
        'cache': str(cache),
        'warning': 'Offline translation only; game must be recompiled/reinstalled with this cache. Rendering unverified.',
    }
    (output / 'runtime-shader-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('build/fable2-runtime-shaders'))
    p.add_argument('--guest-image', type=Path, required=True, help='Previously decoded Fable II guest image')
    for name in ('translator', 'header', 'rehost', 'wrap-vs', 'wrap-ps', 'rename'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    try:
        report = compile_captures(a.capture_dir, a.output, a.guest_image,
                                  a.translator, a.header, a.rehost,
                                  a.wrap_vs, a.wrap_ps, a.rename)
    except (ValueError, OSError, UnicodeError) as error:
        p.exit(2, f'BLOCKED: {error}\n')
    print('Produced runtime shader cache for recompilation: ' + report['cache'])
    print('Translated', report['capture_count'], 'captured shaders; rehosted', report['rehosted_count'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
