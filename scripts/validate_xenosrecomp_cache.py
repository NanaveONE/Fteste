#!/usr/bin/env python3
"""Validate real XenosRecomp's Zstandard + SMOL-V cache and input coverage.

Important: XenosRecomp stores SMOL-V, not plain SPIR-V, in the zstd array.
This is a structural audit, NOT full spirv-val or Vulkan rendering validation.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
from pathlib import Path
import re
import shutil
import subprocess


class CacheError(ValueError):
    pass


def zstd_decode(compressed: bytes, expected: int) -> bytes:
    if not 0 < expected <= 512 * 1024 * 1024:
        raise CacheError('Uncompressed cache size out of bounds')
    name = ctypes.util.find_library('zstd')
    if name:
        library = ctypes.CDLL(name)
        library.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_decompress.restype = ctypes.c_size_t
        library.ZSTD_isError.argtypes = [ctypes.c_size_t]
        library.ZSTD_isError.restype = ctypes.c_uint
        dst = ctypes.create_string_buffer(expected)
        src = ctypes.create_string_buffer(compressed)
        count = library.ZSTD_decompress(dst, expected, src, len(compressed))
        if library.ZSTD_isError(count) or count != expected:
            raise CacheError('Invalid zstd cache or decompressed length')
        return dst.raw
    zstd = shutil.which('zstd')
    if not zstd:
        raise CacheError('zstd or libzstd required')
    proc = subprocess.run([zstd, '-dcq'], input=compressed, capture_output=True, check=False)
    if proc.returncode != 0 or len(proc.stdout) != expected:
        raise CacheError('Invalid zstd cache or decompressed length')
    return proc.stdout


def inspect_cpp(path: Path, scan_dir: Path, min_coverage: float = 1.0) -> dict:
    if not (0 < min_coverage <= 1):
        raise CacheError('Invalid minimum coverage')
    source = path.read_text(encoding='utf-8')
    try:
        raw_entries = source.split('ShaderCacheEntry g_shaderCacheEntries[] = {', 1)[1].split('};', 1)[0]
    except IndexError as exc:
        raise CacheError('XenosRecomp entries array missing') from exc
    row = re.compile(r'\{\s*0x[\da-fA-F]+,\s*\d+,\s*\d+,\s*(\d+),\s*(\d+),\s*\d+,\s*\d+,\s*\d+,\s*"([^"]+)"\s*\}')
    entries = [row.search(line) for line in raw_entries.splitlines() if line.strip()]
    if not entries or any(item is None for item in entries):
        raise CacheError('Empty or invalid XenosRecomp entries')
    cm = re.search(r'g_compressedSpirvCache\[\]\s*=\s*\{([^}]*)\}', source, re.S)
    um = re.search(r'g_spirvCacheDecompressedSize\s*=\s*(\d+)', source)
    cs = re.search(r'g_spirvCacheCompressedSize\s*=\s*(\d+)', source)
    if not all((cm, um, cs)):
        raise CacheError('Missing compressed cache metadata')
    try:
        compressed = bytes(int(n) for n in cm.group(1).split(',') if n.strip())
    except (ValueError, OverflowError) as exc:
        raise CacheError('Corrupt compressed cache initializer') from exc
    if len(compressed) != int(cs.group(1)):
        raise CacheError('Compressed cache length mismatch')
    blob = zstd_decode(compressed, int(um.group(1)))
    expected = {p.name.casefold() for p in scan_dir.glob('*.bin') if p.name.startswith(('PS_', 'VS_'))}
    if not expected:
        raise CacheError('No private Xenos PS_/VS_ inputs')
    visited = set()
    ranges = []
    unmatched = 0
    duplicate = 0
    stages = {'PS': 0, 'VS': 0}
    for item in entries:
        offset, size, path_in_cpp = item.groups()
        offset, size = int(offset), int(size)
        name = Path(path_in_cpp.replace('\\', '/')).name.casefold()
        if name not in expected:
            unmatched += 1
            continue
        if name in visited:
            duplicate += 1
        visited.add(name)
        stages[name[:2].upper()] += 1
        # Real XenosRecomp stores SMOL-V (bytes 'LOMS'), NOT raw SPIR-V.
        if size < 20 or offset < 0 or offset + size > len(blob) or blob[offset:offset+4] != b'LOMS':
            raise CacheError(f'Invalid SMOL-V module boundaries for {name}')
        ranges.append((offset, offset+size))
    ranges.sort()
    if not ranges or ranges[0][0] != 0 or ranges[-1][1] != len(blob) or any(
            ranges[i][1] != ranges[i+1][0] for i in range(len(ranges)-1)):
        raise CacheError('SMOL-V cache slices do not cover the decompressed array exactly')
    covered = len(visited)
    ratio = covered / len(expected)
    ok = ratio >= min_coverage and not unmatched and not duplicate
    return {
        'state': 'PASS' if ok else 'INCOMPLETE',
        'expected': len(expected), 'compiled': covered, 'missing': len(expected)-covered,
        'coverage_percent': round(ratio*100, 2),
        'vertex': stages['VS'], 'pixel': stages['PS'],
        'unmatched': unmatched, 'duplicate': duplicate,
        'compressed_zstd_bytes': len(compressed),
        'uncompressed_smol_bytes': len(blob),
        'validation': 'zstd decompression and per-shader SMOL-V magic/offset verification',
        'warning': 'Does not run SPIRV-Tools spirv-val or verify Vulkan/EDRAM rendering.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--scan-dir', required=True, type=Path)
    parser.add_argument('--min-coverage', type=float, default=1.0)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--spirv-val', action='store_true')
    a = parser.parse_args()
    if a.spirv_val:
        parser.exit(2, 'BLOCKED: SMOL-V must be decoded back to SPIR-V before spirv-val can run.\n')
    try:
        data = inspect_cpp(a.cache, a.scan_dir, a.min_coverage)
    except (OSError, UnicodeError, CacheError) as error:
        parser.exit(2, f'BLOCKED: {error}\n')
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
    print(f'{data["state"]}: {data["compiled"]}/{data["expected"]} shaders translated ({data["coverage_percent"]}%)')
    return 0 if data['state'] == 'PASS' else 2



# Backwards-compatible API used by tests/test_xenosrecomp_cache_validation.py
# from integration 11. That test used synthetic *uncompressed SPIR-V modules*
# whereas the real XenosRecomp produces compressed *SMOL-V modules*.
# Both formats must be distinguished. Never label SMOL-V as validated SPIR-V.
def extract_cpp_cache(source: str) -> tuple[list[dict], bytes, int]:
    """Parse the C++ cache and return entries, zstd bytes, decompressed size."""
    match = re.search(r'ShaderCacheEntry\s+g_shaderCacheEntries\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;', source, re.S)
    if not match:
        raise CacheError('XenosRecomp entries array missing')
    entry_pattern = re.compile(
        r'^\s*\{\s*(0[xX][0-9a-fA-F]+)\s*,\s*\d+\s*,\s*\d+\s*,\s*'
        r'(\d+)\s*,\s*(\d+)\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*"([^"]*)"\s*\},?\s*$'
    )
    entries = []
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        row = entry_pattern.fullmatch(line)
        if not row:
            raise CacheError('Unrecognized shader cache entry')
        shader_hash, off, length, filename = row.groups()
        entries.append({'hash': int(shader_hash, 16), 'spirv_offset': int(off),
                        'spirv_size': int(length), 'source': filename})
    if not entries:
        raise CacheError('EMPTY XenosRecomp shader cache')
    cm = re.search(r'g_compressedSpirvCache\[\]\s*=\s*\{([^}]*)\}', source, re.S)
    um = re.search(r'g_spirvCacheDecompressedSize\s*=\s*(\d+)', source)
    cs = re.search(r'g_spirvCacheCompressedSize\s*=\s*(\d+)', source)
    if not all((cm, um, cs)):
        raise CacheError('Missing compressed shader cache metadata')
    try:
        payload = bytes(int(part.strip(), 0) for part in cm.group(1).split(',') if part.strip())
    except (ValueError, OverflowError) as err:
        raise CacheError('Invalid compressed zstd bytes') from err
    if len(payload) != int(cs.group(1)):
        raise CacheError('Compressed cache size mismatch')
    return entries, payload, int(um.group(1))


def inspect_spirv(data: bytes, *, offset: int, size: int) -> None:
    """Inspect bare SPIR-V *only* (not the SMOL-V used by real Fable II)."""
    import struct
    if size < 20 or offset < 0 or size % 4 or offset + size > len(data):
        raise CacheError('SPIR-V size or alignment invalid')
    magic, version, _generator, bound, schema = struct.unpack_from('<5I', data, offset)
    if magic != 0x07230203:
        raise CacheError('SPIR-V magic does not match')
    if not (0x10000 <= version < 0x20000 and bound > 0 and schema == 0):
        raise CacheError('SPIR-V header invalid')
    end = offset + size
    at = offset + 20
    if at == end:
        raise CacheError('SPIR-V has no instructions')
    while at < end:
        words = struct.unpack_from('<I', data, at)[0] >> 16
        if not words or at + words * 4 > end:
            raise CacheError('Invalid SPIR-V instruction word count')
        at += words * 4


def audit_cache(source: Path, scan_dir: Path, *, required_coverage: float = 1.0,
                run_spirv_val: bool = False) -> dict:
    """Legacy entry point plus explicit recognition of real SMOL-V outputs.

    Existing test fixtures are raw SPIR-V, while real XenosRecomp caches use
    SMOL-V (LOMS). For SMOL-V, delegate to the stricter real-cache inspector.
    """
    if not 0 < required_coverage <= 1:
        raise CacheError('Invalid required coverage')
    entries, compressed, size = extract_cpp_cache(source.read_text(encoding='utf-8'))
    blob = zstd_decode(compressed, size)
    first = entries[0]['spirv_offset']
    if first < 0 or first + 4 > len(blob):
        raise CacheError('Shader cache offset outside decompressed array')
    if blob[first:first + 4] == b'LOMS':
        if run_spirv_val:
            raise CacheError('SMOL-V must be decoded to SPIR-V before spirv-val')
        real = inspect_cpp(source, scan_dir, required_coverage)
        return {
            **real,
            'expected_containers': real['expected'],
            'compiled_containers': real['compiled'],
            'missing_containers': real['missing'],
            'compiled_vertex_shaders': real['vertex'],
            'compiled_pixel_shaders': real['pixel'],
            'unmatched_cache_entries': real['unmatched'],
            'duplicate_cache_entries': real['duplicate'],
            'validation_level': real['validation'],
        }
    if blob[first:first + 4] != b'\x03\x02\x23\x07':
        raise CacheError('Neither SMOL-V nor SPIR-V shader module recognized')
    if run_spirv_val:
        raise CacheError('Legacy SPIR-V fixture validation only; use standalone spirv-val for full validation')
    expected = {p.name.casefold() for p in scan_dir.glob('*.bin') if p.name.startswith(('PS_', 'VS_'))}
    if not expected:
        raise CacheError('No private shader containers')
    seen: set[str] = set()
    duplicate = unmatched = 0
    vertex = pixel = 0
    ranges = []
    for entry in entries:
        off, length = entry['spirv_offset'], entry['spirv_size']
        inspect_spirv(blob, offset=off, size=length)
        ranges.append((off, off + length))
        name = Path(entry['source'].replace('\\', '/')).name.casefold()
        if name not in expected:
            unmatched += 1
            continue
        if name in seen:
            duplicate += 1
        seen.add(name)
        if name.startswith('vs_'):
            vertex += 1
        elif name.startswith('ps_'):
            pixel += 1
    # Detect gaps and out-of-bounds regardless of how many inputs compiled.
    end = 0
    for start, stop in sorted(set(ranges)):
        if start > end:
            raise CacheError('Gap in shader cache bytes')
        end = max(stop, end)
    if end != len(blob):
        raise CacheError('Trailing shader cache bytes')
    covered = len(seen)
    coverage = covered / len(expected)
    return {
        'state': 'PASS' if coverage >= required_coverage and not duplicate and not unmatched else 'INCOMPLETE',
        'expected_containers': len(expected), 'compiled_containers': covered,
        'missing_containers': len(expected) - covered, 'coverage_percent': round(coverage * 100, 2),
        'compiled_vertex_shaders': vertex, 'compiled_pixel_shaders': pixel,
        'unmatched_cache_entries': unmatched, 'duplicate_cache_entries': duplicate,
        'validation_level': 'Synthetic/legacy raw SPIR-V word structure',
        'warning': 'Raw SPIR-V fixtures are not the real XenosRecomp SMOL-V output',
    }

if __name__ == '__main__':
    raise SystemExit(main())
