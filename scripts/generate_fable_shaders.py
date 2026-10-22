#!/usr/bin/env python3
"""Generate Fable II-specific offline Xenos shader cache (NOT Burnout's).

Uses Xerenge's dump_xex_image utility + XenosRecomp host shader translator.
The executable dump utility currently understands BASIC-compressed XEX2 only.
For other XEX formats an independently obtained *decoded guest image* can be
provided with --guest-image, so the tool never tries to bypass DRM itself.

This generates build artifacts *locally*; proprietary game input stays private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


CACHE_SYMBOLS = (
    'g_shaderCacheEntries',
    'g_shaderCacheEntryCount',
    'g_compressedSpirvCache',
    'g_spirvCacheCompressedSize',
    'g_shaderMicrocodeEntries',
    'g_shaderMicrocodeEntryCount',
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def must_be_file(path: Path, name: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f'{name} not found: {path}')
    return path


def must_be_executable(path: Path, name: str) -> Path:
    path = must_be_file(path, name)
    if not os.access(path, os.X_OK):
        raise ValueError(f'{name} not executable: {path}')
    return path


def cache_is_usable(content: str) -> bool:
    if any(not re.search(r'\b' + re.escape(name) + r'\b', content) for name in CACHE_SYMBOLS):
        return False
    # An empty scan may still emit a valid C++ cache. Don't advertise it as
    # covering Fable II or ship it as a renderer cache.
    for name in ('g_shaderCacheEntryCount', 'g_spirvCacheCompressedSize'):
        if re.search(r'\b' + name + r'\s*=\s*0\s*;', content):
            return False
    return True


def create_cache(game_xex: Path | None, guest_image: Path | None, output: Path,
                 dumper: Path | None, translator: Path, header: Path) -> dict:
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f'Output exists; preserving previous results: {output}')
    if game_xex and guest_image:
        raise ValueError('Supply --game-xex OR --guest-image, never both')
    if not game_xex and not guest_image:
        raise ValueError('--game-xex or --guest-image is required')
    translator = must_be_executable(translator, 'XenosRecomp')
    header = must_be_file(header, 'Xenos shader_common.h')
    input_file = must_be_file(game_xex or guest_image, 'Shader input')
    if game_xex:
        dumper = must_be_executable(dumper, 'dump_xex_image') if dumper else None
        if dumper is None:
            raise ValueError('Set --xex-dumper with --game-xex')
        with input_file.open('rb') as f:
            if f.read(4) != b'XEX2':
                raise ValueError('Game executable is not XEX2')
    if output == input_file.parent or input_file in output.parents:
        raise ValueError('Output must be outside the original game content folder')
    output.mkdir(parents=True)
    scan = output / 'xenos-scan'
    scan.mkdir()
    guest = scan / 'guest-image.bin'
    if guest_image:
        shutil.copyfile(input_file, guest)
    else:
        try:
            subprocess.run([str(dumper), str(input_file), '-o', str(guest)], check=True)
        except subprocess.CalledProcessError as exc:
            raise ValueError('XEX decoding failed. Xerenge dumper currently supports BASIC XEX compression only; '
                             'use --guest-image with a legitimately decoded image instead.') from exc
    if not guest.is_file() or guest.stat().st_size == 0:
        raise ValueError('Decoder produced no guest image')
    hlsl = output / 'xenos-hlsl'
    hlsl.mkdir()
    cache = output / 'shader_cache.cpp'
    env = os.environ.copy()
    env['XENOS_RECOMP_DUMP_SOURCE_DIR'] = str(hlsl)
    subprocess.run([str(translator), str(scan), str(cache), str(header)], check=True, env=env)
    if not cache.is_file():
        raise ValueError('Shader translator did not generate shader_cache.cpp')
    source = cache.read_text(encoding='utf-8', errors='replace')
    if not cache_is_usable(source):
        raise ValueError('Generated shader cache lacks required entries/data; cannot build real renderer')
    shader_hlsl = sorted(hlsl.glob('*.hlsl'))
    metadata = {
        'source_title': 'Fable II',
        'input_kind': 'game_xex' if game_xex else 'decoded_guest_image',
        'input_sha256': sha256(input_file),
        'guest_image_sha256': sha256(guest),
        'cache_sha256': sha256(cache),
        'hlsl_files': len(shader_hlsl),
        'hlsl_hashes': [x.stem for x in shader_hlsl if re.fullmatch(r'[0-9a-fA-F]{16}', x.stem)],
        'shader_cache': str(cache),
        'shader_hlsl': str(hlsl),
        'warning': 'Static XEX shaders only; runtime-generated shaders and GPU compatibility remain unverified.',
    }
    (output / 'fable-shader-report.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--game-xex', type=Path)
    src.add_argument('--guest-image', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/fable2-shaders'))
    parser.add_argument('--xex-dumper', type=Path, help='Xerenge host tools/bin/dump_xex_image')
    parser.add_argument('--translator', type=Path, required=True, help='XenosRecomp host binary')
    parser.add_argument('--header', type=Path, required=True, help='XenosRecomp shader_common.h')
    args = parser.parse_args()
    try:
        result = create_cache(args.game_xex, args.guest_image, args.output,
                              args.xex_dumper, args.translator, args.header)
    except (ValueError, OSError, subprocess.CalledProcessError) as err:
        parser.exit(2, f'BLOCKED: {err}\n')
    print(f'Generated Fable-specific GPU cache: {result["shader_cache"]}')
    print(f'HLSL sources: {result["hlsl_files"]}  (static XEX scan, not full shader coverage)')
    print('Next: bash scripts/build_fable_gpu.sh (requires compatible NDK/SDK and Plume checkout)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
