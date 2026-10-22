#!/usr/bin/env python3
"""Audit a REAL XenosRecomp generated C++ cache and its decompressed SPIR-V.

Never generates replacement/fake shaders. No game data or shader bytes are
included in the JSON report. Must be run before linking the Vulkan plugin.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from collections import Counter


ENTRY_SECTION = re.compile(r'\bShaderCacheEntry\s+g_shaderCacheEntries\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;', re.S)
ENTRY_LINE = re.compile(
    r'^\s*\{\s*(0[xX][\da-fA-F]+)\s*,\s*'
    r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'
    r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"([^"]*)"\s*\},?\s*$')
COMPRESSED = re.compile(r'\b(?:extern\s+)?const\s+uint8_t\s+g_compressedSpirvCache\[\s*\]\s*=\s*\{(.*?)\}\s*;', re.S)
DECOMPRESSED_SIZE = re.compile(r'\bg_spirvCacheDecompressedSize\s*=\s*(\d+)\s*;')
COMPRESSED_SIZE = re.compile(r'\bg_spirvCacheCompressedSize\s*=\s*(\d+)\s*;')
SPIRV_MAGIC = 0x07230203
MAX_CACHE = 512 * 1024 * 1024


class CacheError(ValueError):
    pass


def extract_cpp_cache(source: str) -> tuple[list[dict], bytes, int]:
    section = ENTRY_SECTION.search(source)
    data = COMPRESSED.search(source)
    decompressed = DECOMPRESSED_SIZE.search(source)
    compressed = COMPRESSED_SIZE.search(source)
    if not all((section, data, decompressed, compressed)):
        raise CacheError('XenosRecomp cache format incomplete or changed')
    entries = []
    for line in section.group(1).splitlines():
        if not line.strip():
            continue
        match = ENTRY_LINE.fullmatch(line)
        if not match:
            raise CacheError('Unrecognized/invalid shader cache entry: ' + line[:110])
        values = match.groups()
        entries.append({
            'hash': int(values[0], 16), 'spirv_offset': int(values[3]),
            'spirv_size': int(values[4]), 'source': values[8],
        })
    if not entries:
        raise CacheError('XenosRecomp generated an EMPTY SPIR-V shader cache')
    tokens = [x.strip() for x in data.group(1).split(',') if x.strip()]
    try:
        blob = bytes(int(v, 0) for v in tokens)
    except (ValueError, OverflowError) as err:
        raise CacheError('Invalid zstd array in generated cache') from err
    expected_compressed = int(compressed.group(1))
    expected_uncompressed = int(decompressed.group(1))
    if len(blob) != expected_compressed:
        raise CacheError('Generated compressed array length mismatch')
    if not 0 < expected_uncompressed <= MAX_CACHE:
        raise CacheError('Missing/oversized decompressed shader cache')
    return entries, blob, expected_uncompressed


def decompress_zstd(data: bytes, size: int) -> bytes:
    executable = shutil.which('zstd')
    if executable:
        p = subprocess.run([executable, '-dcq'], input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=False)
        if p.returncode:
            raise CacheError('zstd could not decode XenosRecomp SPIR-V: ' + p.stderr.decode(errors='replace')[:300])
        decoded = p.stdout
    else:
        name = ctypes.util.find_library('zstd')
        if not name:
            raise CacheError('zstd decoder not installed: install zstd or libzstd')
        lib = ctypes.CDLL(name)
        lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        lib.ZSTD_decompress.restype = ctypes.c_size_t
        lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        lib.ZSTD_isError.restype = ctypes.c_uint
        output = ctypes.create_string_buffer(size)
        source = ctypes.create_string_buffer(data)
        actual = lib.ZSTD_decompress(output, size, source, len(data))
        if lib.ZSTD_isError(actual):
            raise CacheError('libzstd failed to decode generated SPIR-V cache')
        decoded = output.raw[:actual]
    if len(decoded) != size:
        raise CacheError(f'Decompressed shader bytes {len(decoded)} != declared {size}')
    return decoded


def inspect_spirv(data: bytes, *, offset: int, size: int) -> None:
    if size < 20 or size % 4 or offset < 0 or offset + size > len(data):
        raise CacheError('Shader SPIR-V slice is empty, unaligned, or out of bounds')
    magic, version, generator, bound, schema = struct.unpack_from('<5I', data, offset)
    if magic != SPIRV_MAGIC:
        raise CacheError('Shader SPIR-V magic does not match a compiled module')
    if not (0x10000 <= version < 0x20000 and bound > 0 and schema == 0):
        raise CacheError('Shader SPIR-V header invalid')
    # Check the instruction word stream without assuming any vendor extension.
    cursor = offset + 20
    end = offset + size
    if cursor == end:
        raise CacheError('SPIR-V module has no instructions')
    while cursor < end:
        first_word = struct.unpack_from('<I', data, cursor)[0]
        words = first_word >> 16
        if not words or cursor + words * 4 > end:
            raise CacheError('Malformed SPIR-V instruction word count')
        cursor += words * 4


def audit_cache(source: Path, scan_dir: Path, *, required_coverage: float = 1.0,
                run_spirv_val: bool = False) -> dict:
    if not 0.0 < required_coverage <= 1.0:
        raise CacheError('required_coverage must be between 0 and 1')
    if not scan_dir.is_dir():
        raise CacheError('Private Xenos scan directory missing')
    expected = {}
    for path in scan_dir.glob('*.bin'):
        if path.name.startswith(('PS_', 'VS_')):
            expected[path.name.casefold()] = path
    if not expected:
        raise CacheError('No shader containers (PS_/VS_*.bin) in private scan directory')
    text = source.read_text(encoding='utf-8')
    entries, compressed, declared_size = extract_cpp_cache(text)
    decoded = decompress_zstd(compressed, declared_size)
    from_cache = Counter()
    unmatched = 0
    duplicates = 0
    visited = set()
    val = shutil.which('spirv-val') if run_spirv_val else None
    if run_spirv_val and not val:
        raise CacheError('--spirv-val requested but spirv-val is unavailable')
    for entry in entries:
        name = Path(entry['source'].replace('\\', '/')).name.casefold()
        if name not in expected:
            unmatched += 1
            continue
        if name in visited:
            duplicates += 1
        visited.add(name)
        inspect_spirv(decoded, offset=entry['spirv_offset'], size=entry['spirv_size'])
        from_cache[name[:2].upper()] += 1
        if val:
            code = decoded[entry['spirv_offset']:entry['spirv_offset'] + entry['spirv_size']]
            result = subprocess.run([val, '--target-env', 'vulkan1.1', '-'], input=code,
                                    capture_output=True, check=False)
            if result.returncode:
                raise CacheError(f'spirv-val rejected {name}: {result.stderr.decode(errors="replace")[:300]}')
    covered = len(visited)
    expected_stages = Counter(name[:2].upper() for name in expected)
    return {
        'state': 'PASS' if (not unmatched and not duplicates and
                            covered / len(expected) >= required_coverage) else 'INCOMPLETE',
        'expected_containers': len(expected), 'compiled_containers': covered,
        'missing_containers': len(expected) - covered, 'coverage_percent': round(covered * 100 / len(expected), 2),
        'expected_vertex_shaders': expected_stages['VS'], 'expected_pixel_shaders': expected_stages['PS'],
        'compiled_vertex_shaders': from_cache['VS'], 'compiled_pixel_shaders': from_cache['PS'],
        'unmatched_cache_entries': unmatched, 'duplicate_cache_entries': duplicates,
        'uncompressed_spirv_bytes': len(decoded),
        'validation_level': 'SPIR-V header/word structure' + (' + spirv-val Vulkan1.1' if val else ''),
        'minimum_coverage': required_coverage,
        'warning': 'Valid SPIR-V modules do NOT prove Fable II Vulkan/EDRAM gameplay compatibility.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--scan-dir', required=True, type=Path)
    parser.add_argument('--min-coverage', type=float, default=1.0)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--spirv-val', action='store_true')
    args = parser.parse_args()
    try:
        result = audit_cache(args.cache, args.scan_dir,
                             required_coverage=args.min_coverage,
                             run_spirv_val=args.spirv_val)
    except (CacheError, OSError, UnicodeError) as e:
        parser.exit(2, f'BLOCKED: {e}\n')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{result["state"]}: SPIR-V {result["compiled_containers"]}/{result["expected_containers"]} '
          f'({result["coverage_percent"]}%) VS={result["compiled_vertex_shaders"]}, '
          f'PS={result["compiled_pixel_shaders"]}')
    if result['state'] != 'PASS':
        print(f'BLOCKED: {result["missing_containers"]} shaders were not translated '
              f'or {result["unmatched_cache_entries"]} entries did not match the private shader scan')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
