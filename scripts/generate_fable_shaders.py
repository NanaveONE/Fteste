#!/usr/bin/env python3
"""Generate Fable II-specific offline Xenos shader cache (NOT Burnout's).

Prefers Fable II ShaderBankFile .sbk data (extracted locally) + XenosRecomp.
Can also scan a decoded XEX guest image, but Fable II shaders are in SBK.
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

try:
    from scripts.extract_fable_sbk import extract_banks
except ModuleNotFoundError:  # executed as python scripts/generate_fable_shaders.py
    from extract_fable_sbk import extract_banks


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
                 dumper: Path | None, translator: Path, header: Path,
                 *, shader_banks: list[Path] | None = None) -> dict:
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f'Output exists; preserving previous results: {output}')
    chosen = int(bool(game_xex)) + int(bool(guest_image)) + int(bool(shader_banks))
    if chosen != 1:
        raise ValueError('Supply exactly one of --game-xex, --guest-image or --shader-banks')
    translator = must_be_executable(translator, 'XenosRecomp')
    header = must_be_file(header, 'Xenos shader_common.h')
    input_file = must_be_file(game_xex or guest_image, 'Shader input') if not shader_banks else None
    if game_xex:
        dumper = must_be_executable(dumper, 'dump_xex_image') if dumper else None
        if dumper is None:
            raise ValueError('Set --xex-dumper with --game-xex')
        with input_file.open('rb') as f:
            if f.read(4) != b'XEX2':
                raise ValueError('Game executable is not XEX2')
    bank_report = None
    if shader_banks:
        # The extractor validates BOTH the compressed SBK streams and Xenos
        # container layouts. The tool reads each original bank locally and
        # writes private containers only inside ignored build/.
        bank_report = extract_banks(shader_banks, output)
        scan = output / 'xenos-scan'
        guest = None
    else:
        if output == input_file.parent or input_file in output.parents:
            raise ValueError('Output must be outside original game content')
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
                raise ValueError('XEX decoding failed; use SBK banks or a decoded guest image.') from exc
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
        'input_kind': ('shader_banks' if shader_banks else
                       ('game_xex' if game_xex else 'decoded_guest_image')),
        'input_sha256': sha256(input_file) if input_file else None,
        'guest_image_sha256': sha256(guest) if guest else None,
        'shader_banks': bank_report['banks'] if bank_report else [],
        'extracted_containers': bank_report['unique_containers'] if bank_report else None,
        'cache_sha256': sha256(cache),
        'hlsl_files': len(shader_hlsl),
        'hlsl_hashes': [x.stem for x in shader_hlsl if re.fullmatch(r'[0-9a-fA-F]{16}', x.stem)],
        'shader_cache': str(cache),
        'shader_hlsl': str(hlsl),
        'warning': 'SBK shaders are static content. Runtime-created shaders and GPU rendering remain unverified.',
    }
    (output / 'fable-shader-report.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--game-xex', type=Path)
    src.add_argument('--guest-image', type=Path)
    src.add_argument('--shader-banks', type=Path, nargs='+',
                     help='Fable II data/Shaders/Shaders[Release].sbk from your own dump')
    parser.add_argument('--output', type=Path, default=Path('build/fable2-shaders'))
    parser.add_argument('--xex-dumper', type=Path, help='Xerenge host tools/bin/dump_xex_image')
    parser.add_argument('--translator', type=Path, required=True, help='XenosRecomp host binary')
    parser.add_argument('--header', type=Path, required=True, help='XenosRecomp shader_common.h')
    args = parser.parse_args()
    try:
        result = create_cache(args.game_xex, args.guest_image, args.output,
                              args.xex_dumper, args.translator, args.header,
                              shader_banks=args.shader_banks)
    except (ValueError, OSError, subprocess.CalledProcessError) as err:
        parser.exit(2, f'BLOCKED: {err}\n')
    print(f'Generated Fable-specific GPU cache: {result["shader_cache"]}')
    print(f'HLSL sources: {result["hlsl_files"]}  (SBK or XEX static scan; runtime coverage unverified)')
    print('Next: bash scripts/build_fable_gpu.sh (requires compatible NDK/SDK and Plume checkout)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
