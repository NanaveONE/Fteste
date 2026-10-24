#!/usr/bin/env python3
"""Check ReXGlue C++ imports against authentic Android ARM64 ELF exports.

Checks a PRIVATE Integration57 bundle before the workflow uploads it. This is
not a dynamic loader test, production shader authorization, or playable APK.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

LIBRARIES = (
    'libfable2.so', 'librexgpu-plume.so', 'librexruntime.so', 'libc++_shared.so',
)
REX_MANGLED_PREFIXES = ('_ZN3rex', '_ZNK3rex', '_ZTVN3rex', '_ZTIN3rex', '_ZTSN3rex')
ROW = re.compile(
    r'^\s*\d+:\s+\S+\s+\d+\s+\S+\s+(GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)(?:\s|$)'
)
MAX_LIB_BYTES = 512 * 1024 * 1024


class AbiBlocked(ValueError):
    pass


def parse_dynsym(contents: str) -> tuple[set[str], set[str]]:
    """Return externally defined and non-weak undefined dynamic ELF symbols."""
    defined: set[str] = set()
    required: set[str] = set()
    for line in contents.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        binding, index, value = match.groups()
        name = value.split('@', 1)[0]
        if not name:
            continue
        if index == 'UND':
            if binding == 'GLOBAL':
                required.add(name)
        else:
            defined.add(name)
    return defined, required


def read_dynsym(readelf: str, lib: Path) -> tuple[set[str], set[str]]:
    result = subprocess.run(
        [readelf, '--dyn-syms', '--wide', str(lib)],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise AbiBlocked(f'Cannot read dynamic ELF symbols from {lib.name}: {result.stderr[-300:]}')
    defined, required = parse_dynsym(result.stdout)
    if not defined or not required:
        raise AbiBlocked(f'No usable dynamic ELF symbols for {lib.name}; reject silent ABI check')
    return defined, required


def check_symbols(symbols: dict[str, tuple[set[str], set[str]]]) -> dict:
    if set(symbols) != set(LIBRARIES):
        raise AbiBlocked('Expected all four native libraries for ABI inspection')
    definitions = set().union(*(symbols[name][0] for name in LIBRARIES))
    result = {}
    missing = {}
    for source in ('libfable2.so', 'librexgpu-plume.so'):
        imports = {name for name in symbols[source][1]
                   if name.startswith(REX_MANGLED_PREFIXES)}
        if not imports:
            raise AbiBlocked(f'{source}: no ReXGlue imports observed; refuse incomplete symbol table')
        absent = sorted(imports - definitions)
        result[source] = {'rex_import_count': len(imports),
                          'rex_resolved_count': len(imports) - len(absent)}
        if absent:
            missing[source] = absent
    if missing:
        details = '; '.join(
            f'{name}: {len(values)} unresolved ReXGlue import(s) ' + ', '.join(values[:4])
            for name, values in missing.items()
        )
        raise AbiBlocked(details)
    return result


def audit_bundle(bundle: Path, readelf: str) -> dict:
    if not bundle.is_file():
        raise AbiBlocked('Missing private Integration57 ZIP')
    with tempfile.TemporaryDirectory(prefix='fable2-abi59-') as tmp:
        temp = Path(tmp)
        with ZipFile(bundle) as z:
            names = [entry.filename for entry in z.infolist()]
            expected = {f'lib/arm64-v8a/{name}' for name in LIBRARIES} | {
                'diagnostic/integracao57.json', 'AVISO.txt',
            }
            if len(names) != len(expected) or set(names) != expected:
                raise AbiBlocked('Unexpected/duplicate names in Integration57 private ZIP')
            record = json.loads(z.read('diagnostic/integracao57.json'))
            if record.get('status') != 'PRIVATE_ARM64_NATIVE_INTEGRATION_DIAGNOSTIC_ONLY':
                raise AbiBlocked('Invalid integration provenance')
            if record.get('production_approved') is not False or record.get('apk_generated') is not False:
                raise AbiBlocked('Partial GPU probe must remain diagnostic-only')
            if record.get('gpu_coverage') != {
                'compiled': 583, 'expected': 588, 'missing': 5,
                'missing_hashes': [
                    '17A0FEDEF93DAE25', '1CEC1A730807EC21', '5243696187782727',
                    'AC0C424248A6B1AD', 'DB2ACD9856EB8E28',
                ],
            }:
                raise AbiBlocked('Unexpected shader coverage in integration report')
            for name in LIBRARIES:
                member = z.getinfo(f'lib/arm64-v8a/{name}')
                if not 100 <= member.file_size <= MAX_LIB_BYTES:
                    raise AbiBlocked(f'Invalid ELF size for {name}')
                # Do not accept ZIP symlinks, even with approved names.
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise AbiBlocked(f'Symlink prohibited for {name}')
                target = temp / name
                digest = hashlib.sha256()
                with z.open(member) as src, target.open('wb') as dst:
                    while data := src.read(1 << 20):
                        digest.update(data)
                        dst.write(data)
                expectation = record.get('libraries', {}).get(name, {})
                if expectation.get('sha256') != digest.hexdigest() or expectation.get('bytes') != member.file_size:
                    raise AbiBlocked(f'Native ELF integrity mismatch: {name}')
                with target.open('rb') as elf_file:
                    hdr = elf_file.read(64)
                if (hdr[:6] != b'\x7fELF\x02\x01' or
                        struct.unpack_from('<H', hdr, 16)[0] != 3 or
                        struct.unpack_from('<H', hdr, 18)[0] != 183):
                    raise AbiBlocked(f'Not an ARM64 shared object: {name}')
        symbols = {name: read_dynsym(readelf, temp / name) for name in LIBRARIES}
        result = check_symbols(symbols)
        return {'state': 'PASS_REX_CPP_IMPORTS_ONLY', 'libraries': result,
                'not_verified': 'Android system symbols, SDK ABI/behavior, Vulkan, MemExport, gameplay'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--readelf', required=True)
    args = parser.parse_args()
    try:
        result = audit_bundle(args.bundle, args.readelf)
    except (AbiBlocked, OSError, ValueError, BadZipFile, KeyError) as exc:
        parser.exit(2, f'BLOCKED ABI59: {exc}\n')
    for name, detail in result['libraries'].items():
        print(f'PASS ABI59 {name}: {detail["rex_resolved_count"]}/{detail["rex_import_count"]} ReXGlue symbols resolved')
    print('CAUTION: symbol resolution does not prove binary ABI behavior or gameplay.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
