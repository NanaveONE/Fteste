#!/usr/bin/env python3
"""Private diagnostic staging of Fable II guest + ReXGlue + Plume ARM64.

DOES NOT produce an APK and does not authorize incomplete MemExport shaders
for release. Only run on a PRIVATE runner with owner-supplied game binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

try:
    from scripts import stage_android_libs, check_android_16k_alignment
except ImportError:
    import stage_android_libs
    import check_android_16k_alignment

GPU_LIB = 'librexgpu-plume.so'
ARCHIVE_NAMES = frozenset({GPU_LIB, 'gpu-probe56-report.json',
                           'gpu-probe56-alignment.json', 'AVISO.txt'})
MISSING_HASHES = frozenset({
    '17A0FEDEF93DAE25', '1CEC1A730807EC21', '5243696187782727',
    'AC0C424248A6B1AD', 'DB2ACD9856EB8E28',
})
MAX_GPU_BYTES = 256 * 1024 * 1024


class IntegrationBlocked(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_probe_report(report: dict) -> None:
    """Retain the exact 583/588 *diagnostic* gate; NEVER mark it production."""
    if not isinstance(report, dict):
        raise IntegrationBlocked('GPU probe report is not an object')
    keys = ('expected', 'compiled', 'missing')
    if any(type(report.get(k)) is not int for k in keys):
        raise IntegrationBlocked('GPU coverage counts missing or invalid')
    hashes = report.get('missing_hashes')
    if (not isinstance(hashes, list) or len(hashes) != 5 or
            any(not isinstance(x, str) for x in hashes)):
        raise IntegrationBlocked('Missing shader hashes invalid')
    if (report.get('status') != 'PRIVATE_ARM64_GPU_PROBE56_ONLY'
        or (report['expected'], report['compiled'], report['missing']) != (588, 583, 5)
        or report.get('production_approved') is not False
        or report.get('guest_memexport_execution_proven') is not False
        or set(hashes) != MISSING_HASHES):
        raise IntegrationBlocked('GPU probe must be verified partial 583/588, NOT production')
    if not re.fullmatch('[0-9a-fA-F]{64}', str(report.get('cache_sha256', ''))):
        raise IntegrationBlocked('GPU cache provenance SHA256 absent')


def extract_gpu_probe(archive: Path, output: Path) -> dict:
    """Validate strict ZIP contents, not arbitrary paths or untrusted symlinks."""
    with ZipFile(archive) as z:
        items = z.infolist()
        names = [x.filename for x in items]
        if (len(items) != len(set(names)) or
                not {GPU_LIB, 'gpu-probe56-report.json'}.issubset(names) or
                not set(names).issubset(ARCHIVE_NAMES)):
            raise IntegrationBlocked('Unexpected/duplicate private GPU archive entries')
        for item in items:
            mode = item.external_attr >> 16
            if (item.is_dir() or '/' in item.filename or '\\' in item.filename or
                    (mode & 0o170000) == 0o120000):
                raise IntegrationBlocked('Unsafe GPU archive path or symlink')
        payload = z.getinfo(GPU_LIB)
        if not 100 < payload.file_size < MAX_GPU_BYTES:
            raise IntegrationBlocked('Missing/oversized GPU ARM64 shared library')
        meta = z.getinfo('gpu-probe56-report.json')
        if not 20 < meta.file_size <= 64 * 1024:
            raise IntegrationBlocked('Invalid GPU diagnostic report length')
        report = json.loads(z.read(meta))
        validate_probe_report(report)
        output.write_bytes(z.read(payload))
        if output.stat().st_size != payload.file_size:
            raise IntegrationBlocked('GPU ZIP extraction size mismatch')
        return report


def integrate(game: Path, probe_zip: Path, runtime: Path, output: Path, readelf: str) -> dict:
    """Stage only verified libs and private ZIP, fail closed before output exists."""
    if output.exists():
        raise IntegrationBlocked('Private output already exists; refusing stale overwrite')
    if not runtime.is_dir():
        raise IntegrationBlocked('ReXGlue runtime directory missing')
    if game.name != 'libfable2.so' or not game.is_file():
        raise IntegrationBlocked('Actual private libfable2.so required')
    for name in ('librexruntime.so', 'libc++_shared.so', 'runtime-build-report.json'):
        if not (runtime / name).is_file():
            raise IntegrationBlocked('Runtime artifact is missing ' + name)
    runtime_report = json.loads((runtime / 'runtime-build-report.json').read_text())
    if (runtime_report.get('status') != 'ARM64_ELF_AND_DT_NEEDED_VERIFIED' or
            runtime_report.get('architecture') != 'aarch64'):
        raise IntegrationBlocked('Runtime artifact provenance/status is not verified')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.fable2-integration57-', dir=output.parent) as temp:
        work = Path(temp)
        gpu = work / GPU_LIB
        probe = extract_gpu_probe(probe_zip, gpu)
        staged = work / 'staged'
        files = stage_android_libs.stage(
            [game, gpu, runtime / 'librexruntime.so', runtime / 'libc++_shared.so'],
            [], [runtime], staged, readelf)
        alignment = check_android_16k_alignment.audit(sorted(staged.glob('*.so')))
        if alignment['state'] != 'PASS':
            raise IntegrationBlocked('Native libraries are not all 16 KiB PT_LOAD aligned')
        manifest = {
            'status': 'PRIVATE_ARM64_NATIVE_INTEGRATION_DIAGNOSTIC_ONLY',
            'libraries': {name: {'sha256': sha256((staged / name).read_bytes()),
                                 'bytes': (staged / name).stat().st_size}
                          for name in sorted(files)},
            'gpu_coverage': {'compiled': 583, 'expected': 588, 'missing': 5,
                             'missing_hashes': sorted(MISSING_HASHES)},
            'gpu_cache_sha256': probe['cache_sha256'],
            'elf_16kb_aligned': True,
            'sdk_abi_equivalence_proven': False,
            'vulkan_rendering_proven': False,
            'guest_memexport_execution_proven': False,
            'apk_generated': False,
            'production_approved': False,
            'notes': 'Four-library dependency closure verified; guest build SDK ABI and gameplay require runtime validation. No executable APK.',
        }
        # Private archives contain game-derived native binaries: NEVER publish
        # through the public GitHub Actions artifact endpoint.
        with ZipFile(output, 'x', ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            for path in sorted(staged.glob('*.so')):
                z.write(path, f'lib/arm64-v8a/{path.name}')
            z.writestr('diagnostic/integracao57.json', json.dumps(manifest, indent=2) + '\n')
            z.writestr('AVISO.txt',
                       'DIAGNOSTICO PRIVADO, NAO APK. GPU 583/588, faltam 5 shaders MemExport. '\
                       'Integracao ELF nao prova ABI, Vulkan ou gameplay. NAO distribuir.\n')
        return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game-lib', type=Path, required=True)
    p.add_argument('--gpu-probe-zip', type=Path, required=True)
    p.add_argument('--runtime-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--readelf', required=True)
    a = p.parse_args()
    try:
        result = integrate(a.game_lib, a.gpu_probe_zip, a.runtime_dir, a.output, a.readelf)
    except (IntegrationBlocked, OSError, BadZipFile, KeyError, ValueError) as error:
        p.exit(2, f'BLOCKED INTEGRATION57: {error}\n')
    print('PASS: private ARM64 native libraries staged:', len(result['libraries']))
    print('PROBE ONLY: 583/588 shader coverage; MemExport/gameplay/ABI NOT proven.')
    print('PRIVATE:', a.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
