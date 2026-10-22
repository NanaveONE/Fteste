#!/usr/bin/env python3
"""Extract Fable II Xenos shader containers from ShaderBankFile .sbk files.

The format observed in the GOTY shader banks is a 16-byte magic, a 16-bit
version (0x0300 / 0x0301) and metadata followed by length-prefixed zlib
Z_SYNC_FLUSH blocks. Each inflated block embeds Xenos 0x102A11 containers.

The extraction runs *locally*, never adds game files to source control, and
rejects malformed blocks rather than silently manufacturing shaders.
This is reverse-engineered from user-supplied files; other builds may differ.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import zlib

MAGIC = b'ShaderBankFile\0\0'
SUPPORTED_VERSIONS = frozenset((0x300, 0x301))
XENOS_SHADER_PREFIX = b'\x10\x2a\x11'
ZLIB_SYNC_FLUSH = b'\x00\x00\xff\xff'
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_INFLATED_CHUNK = 32 * 1024 * 1024
MAX_TOTAL_INFLATED = 256 * 1024 * 1024
MAX_BLOCKS = 20000


@dataclass(frozen=True)
class Shader:
    stage: str
    data: bytes
    sha256: str


@dataclass(frozen=True)
class Bank:
    name: str
    version: str
    sha256: str
    compressed_blocks: int
    inflated_bytes: int
    shaders: tuple[Shader, ...]


def _scan_containers(block: bytes) -> list[Shader]:
    result: list[Shader] = []
    at = 0
    while True:
        at = block.find(XENOS_SHADER_PREFIX, at)
        if at == -1:
            break
        if at % 4 or at + 36 > len(block):
            at += 1
            continue
        (flags, virtual_size, physical_size, _reserved, constant_table,
         definition_table, shader_offset, trailer1, trailer2) = struct.unpack_from('>9I', block, at)
        length = virtual_size + physical_size
        if (flags & 0xFFFFFF00 != 0x102A1100 or
                virtual_size < 36 or physical_size == 0 or
                length > len(block) - at or
                trailer1 or trailer2 or
                not (36 <= constant_table <= virtual_size) or
                not (definition_table == 0 or 36 <= definition_table <= virtual_size) or
                not (36 <= shader_offset <= virtual_size)):
            at += 1
            continue
        data = block[at:at + length]
        result.append(Shader('VS' if flags & 1 else 'PS', data, hashlib.sha256(data).hexdigest()))
        at += length
    return result


def _inflate_streams(data: bytes, start: int) -> tuple[list[bytes], int]:
    pos = start
    inflated: list[bytes] = []
    total = 0
    while pos < len(data):
        if len(inflated) >= MAX_BLOCKS or pos + 4 > len(data):
            raise ValueError('Invalid/truncated SBK block table')
        size = int.from_bytes(data[pos:pos + 4], 'big')
        if not 6 <= size <= MAX_CHUNK_BYTES or pos + 4 + size > len(data):
            raise ValueError('Invalid SBK compressed block length')
        compressed = data[pos + 4:pos + 4 + size]
        if compressed[:2] not in (b'\x78\x01', b'\x78\x9c', b'\x78\xda') or not compressed.endswith(ZLIB_SYNC_FLUSH):
            raise ValueError('SBK block is not a Z_SYNC_FLUSH zlib segment')
        try:
            stream = zlib.decompressobj()
            uncompressed = stream.decompress(compressed, MAX_INFLATED_CHUNK + 1)
            if (stream.unconsumed_tail or stream.unused_data or stream.eof or len(uncompressed) > MAX_INFLATED_CHUNK):
                raise ValueError('Unexpected SBK zlib state / oversized block')
            uncompressed += stream.flush()
        except zlib.error as err:
            raise ValueError('Invalid SBK zlib block') from err
        if len(uncompressed) < 20 or int.from_bytes(uncompressed[:4], 'big') != 20:
            raise ValueError('SBK inflated block has invalid header')
        # The offset triplet is a set of increasing table boundaries in each block.
        table_offsets = struct.unpack_from('>3I', uncompressed, 8)
        if not (20 <= table_offsets[0] <= table_offsets[1] <= table_offsets[2] <= len(uncompressed)):
            raise ValueError('SBK inflated block has invalid table boundaries')
        total += len(uncompressed)
        if total > MAX_TOTAL_INFLATED:
            raise ValueError('SBK inflated data exceeds safety limit')
        inflated.append(uncompressed)
        pos += 4 + size
    if not inflated or pos != len(data):
        raise ValueError('SBK payload incomplete')
    return inflated, total


def parse_bank(data: bytes, *, filename: str = 'bank.sbk') -> Bank:
    if len(data) > MAX_INPUT_BYTES or len(data) < 64 or not data.startswith(MAGIC):
        raise ValueError('Not a supported ShaderBankFile / file too large')
    version = int.from_bytes(data[16:19], 'big')
    if data[19] != 0:
        raise ValueError('Unexpected SBK version marker')
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f'Unsupported ShaderBankFile version 0x{version:04X}')
    # The metadata has variable length. Find the first length-prefixed zlib
    # stream that produces a valid complete chain all the way to file EOF.
    starts: list[int] = []
    for header in (b'\x78\x01', b'\x78\x9c', b'\x78\xda'):
        at = 24
        while True:
            at = data.find(header, at)
            if at == -1:
                break
            if at >= 4 and data[at - 4:at] != b'\0\0\0\0':
                starts.append(at - 4)
            at += 2
    for start in sorted(set(starts)):
        try:
            chunks, total = _inflate_streams(data, start)
        except ValueError:
            continue
        if not all(_scan_containers(chunk) for chunk in chunks):
            continue
        return Bank(filename, f'0x{version:04X}', hashlib.sha256(data).hexdigest(),
                    len(chunks), total,
                    tuple(shader for chunk in chunks for shader in _scan_containers(chunk)))
    raise ValueError('Could not find complete length-prefixed SBK shader blocks')


def extract_banks(paths: list[Path], output: Path) -> dict:
    if not paths or len(paths) > 16:
        raise ValueError('Supply between 1 and 16 SBK files')
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f'Output already exists: {output}')
    banks: list[Bank] = []
    seen_inputs: set[Path] = set()
    for original in paths:
        path = original.expanduser().resolve()
        if path in seen_inputs or not path.is_file() or path.suffix.lower() != '.sbk':
            raise ValueError(f'Invalid/duplicate SBK file: {path}')
        if (output == path.parent or
                (path.parent.name.casefold() == 'shaders' and
                 path.parent.parent.name.casefold() == 'data' and
                 path.parent.parent in output.parents)):
            raise ValueError('Output must not be inside an input data folder')
        seen_inputs.add(path)
        banks.append(parse_bank(path.read_bytes(), filename=path.name))
    unique: dict[str, Shader] = {}
    for bank in banks:
        for shader in bank.shaders:
            unique.setdefault(shader.sha256, shader)
    if not unique:
        raise ValueError('SBK contained no supported shaders')
    scan_dir = output / 'xenos-scan'
    scan_dir.mkdir(parents=True)
    for digest, shader in sorted(unique.items()):
        (scan_dir / f'{shader.stage}_{digest}.bin').write_bytes(shader.data)
    stages = {'VS': sum(s.stage == 'VS' for s in unique.values()),
              'PS': sum(s.stage == 'PS' for s in unique.values())}
    report = {
        'format': 'Fable II ShaderBankFile / XenosRecomp containers',
        'banks': [{'filename': b.name, 'version': b.version,
                   'sha256': b.sha256, 'compressed_blocks': b.compressed_blocks,
                   'inflated_bytes': b.inflated_bytes, 'shader_containers': len(b.shaders)}
                  for b in banks],
        'unique_containers': len(unique),
        'vertex_shaders': stages['VS'],
        'pixel_shaders': stages['PS'],
        'duplicate_containers_across_banks': sum(len(b.shaders) for b in banks) - len(unique),
        'note': 'Extracted shader binaries are private game material; do not commit output to GitHub.',
    }
    (output / 'sbk-analysis.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--banks', type=Path, nargs='+', required=True,
                    help='Original data/shaders/*.sbk paths (one or both)')
    ap.add_argument('--output', type=Path, required=True,
                    help='Private local output directory, e.g. build/sbk-extracted')
    a = ap.parse_args()
    try:
        report = extract_banks(a.banks, a.output)
    except (ValueError, OSError) as e:
        ap.exit(2, f'BLOCKED: {e}\n')
    print(f'Extracted {report["unique_containers"]} unique Xenos shaders: '
          f'{report["vertex_shaders"]} VS, {report["pixel_shaders"]} PS')
    print(f'Private container output: {a.output / "xenos-scan"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
