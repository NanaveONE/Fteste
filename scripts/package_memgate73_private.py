#!/usr/bin/env python3
"""Fail-closed PRIVATE ARM64 assembly of Memgate73 guest, runtime and GPU.

No gameplay, Vulkan completion, DMA coverage, or MemExport commit permission
is proven by linker checks. The private guest and shader-derived binaries are
never written outside the caller's private destination ZIP.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from check_android_16k_alignment import load_alignments
from verify_rex_abi59 import check_symbols, read_dynsym

PIN = '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b'
GATE = 'libfable2_memgate71.so'
GAME = 'libfable2.so'
RUNTIME = 'librexruntime.so'
GPU = 'librexgpu-plume.so'
CXX = 'libc++_shared.so'
CORE = (GAME, RUNTIME, GPU, GATE, CXX)
MAX_LIB_BYTES = 512 * 1024 * 1024
MISSING = sorted(('17A0FEDEF93DAE25', '1CEC1A730807EC21',
                  '5243696187782727', 'AC0C424248A6B1AD', 'DB2ACD9856EB8E28'))
GATE_SYMBOLS = ('fable_memgate71_enter', 'fable_memgate71_leave',
                'fable_memgate71_acquire_diagnostic',
                'fable_memgate71_release_diagnostic',
                'fable_memgate71_snapshot', 'fable_memgate71_commit_permitted')
SYSTEM = frozenset(('libc.so', 'libm.so', 'libdl.so', 'liblog.so',
                   'libandroid.so', 'libvulkan.so', 'libEGL.so',
                   'libGLESv1_CM.so', 'libGLESv2.so', 'libGLESv3.so',
                   'libOpenSLES.so', 'libaaudio.so', 'libz.so',
                   'libatomic.so', 'libunwind.so', 'libstdc++.so',
                   'libjnigraphics.so', 'libmediandk.so',
                   'libnativewindow.so', 'libsync.so', 'libbinder_ndk.so',
                   'libcamera2ndk.so', 'libamidi.so'))
BAD = frozenset(('libburnout.so', 'libmain_eu.so', 'libmain_us.so',
                 'libxerenge_installer.so'))
NEEDED = re.compile(r'\(NEEDED\).*?\[([^\]]+)\]')
SONAME = re.compile(r'\(SONAME\).*?\[([^\]]+)\]')


class Blocked(ValueError):
    pass


def load_json(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(doc, dict):
        raise Blocked('Expected a JSON object')
    return doc


def check_evidence(runtime: dict, plume: dict, shader: dict) -> dict:
    """Require REAL known hooks and incomplete shader status; never certify."""
    if (runtime.get('sdk_pin') != PIN or runtime.get('source_files') != 3 or
            not isinstance(runtime.get('scope_sites'), int) or
            runtime['scope_sites'] < 10 or runtime.get('commit_permitted') is not False):
        raise Blocked('Pinned runtime Memgate72 source coverage report missing or drifted')
    digests = plume.get('transformed')
    originals = plume.get('source')
    plume_files = {'plume_graphics_system.cpp', 'plume_draw.cpp'}
    if (not isinstance(digests, dict) or set(digests) != plume_files or
            not isinstance(originals, dict) or set(originals) != plume_files or
            any(not isinstance(v, str) or re.fullmatch(r'[a-f0-9]{64}', v) is None
                for v in (*digests.values(), *originals.values()))):
        raise Blocked('Plume72 source hash provenance absent or malformed')
    if (plume.get('stage') != 72 or
            plume.get('status') != 'PLUME_KNOWN_CPU_PATHS_ONLY_NOT_CERTIFIED' or
            plume.get('registered_scope_sites') != 7 or
            plume.get('vulkan_device_completion_covered') is not False or
            plume.get('all_dma_paths_covered') is not False or
            plume.get('memexport_commit_permitted') is not False):
        raise Blocked('Plume72 producer hook report missing, drifted or unsafe')
    if (shader.get('status') != 'PRIVATE_ARM64_GPU_PROBE56_ONLY' or
            shader.get('expected') != 588 or shader.get('compiled') != 583 or
            shader.get('missing') != 5 or
            shader.get('missing_hashes') != MISSING or
            shader.get('production_approved') is not False or
            shader.get('guest_memexport_execution_proven') is not False):
        raise Blocked('Shader input identities do not match known 583/588 diagnostic')
    return {'pinned_sdk': PIN, 'runtime_scope_sites': runtime['scope_sites'],
            'plume_scope_sites': 7, 'shader_compiled': 583,
            'shader_expected': 588, 'shader_missing': 5}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for block in iter(lambda: fp.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def ensure_elf(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or not 100 <= path.stat().st_size <= MAX_LIB_BYTES:
        raise Blocked('Missing, symlinked or oversized ARM64 native ELF: ' + path.name)
    # Includes architecture, PT_LOAD congruence and ELF64 checks.
    aligns = load_alignments(path)
    if any(a < 16384 for a in aligns):
        raise Blocked('Native ELF lacks 16 KiB PT_LOAD alignment: ' + path.name)
    return {'bytes': path.stat().st_size, 'sha256': digest(path),
            'min_pt_load_alignment': min(aligns)}


def dynamic(path: Path, readelf: str) -> tuple[set[str], str | None]:
    run = subprocess.run([readelf, '-d', '--wide', str(path)],
                         capture_output=True, text=True, check=False)
    if run.returncode != 0:
        raise Blocked('Cannot inspect ELF dynamic section: ' + path.name)
    names = SONAME.findall(run.stdout)
    if len(names) > 1:
        raise Blocked('Ambiguous ELF SONAME: ' + path.name)
    return set(NEEDED.findall(run.stdout)), names[0] if names else None


def exported(path: Path, readelf: str) -> set[str]:
    run = subprocess.run([readelf, '--dyn-syms', '--wide', str(path)],
                         capture_output=True, text=True, check=False)
    if run.returncode:
        raise Blocked('Cannot read exported dynamic symbols: ' + path.name)
    # Use only non-undefined dynamic entries. Do not confuse an import with an export.
    result = set()
    for line in run.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].rstrip(':').isdigit() and fields[6] != 'UND':
            result.add(fields[7].split('@', 1)[0])
    return result


def inventory(runtime_dir: Path, guest: Path, gate: Path, gpu: Path) -> dict[str, Path]:
    if not runtime_dir.is_dir():
        raise Blocked('Runtime staging directory missing')
    extras = {}
    for item in runtime_dir.iterdir():
        if item.name.endswith('.so'):
            if item.name in (GAME, GPU) or item.name in BAD:
                raise Blocked('Unrelated guest/GPU/game DSO in runtime output')
            if item.name in extras:
                raise Blocked('Duplicate runtime DSO')
            extras[item.name] = item
    for required in (RUNTIME, CXX, GATE):
        if required not in extras:
            raise Blocked('Missing build-time runtime library: ' + required)
    result = {**extras, GAME: guest, GPU: gpu, GATE: gate}
    if len(set(result)) != len(result) or len(result) > 24:
        raise Blocked('Unexpected native library inventory')
    return result


def audit(libraries: dict[str, Path], runtime_gate: Path, readelf: str) -> tuple[dict, dict]:
    records = {}
    dependencies = {}
    for name, path in sorted(libraries.items()):
        record = ensure_elf(path)
        needed, soname = dynamic(path, readelf)
        if soname is not None and soname != name:
            raise Blocked('ELF SONAME does not match staged library: ' + name)
        if needed & BAD:
            raise Blocked('Unexpected unrelated game/runtime ELF dependency: ' + name)
        records[name] = {**record, 'needed': sorted(needed), 'soname': soname}
        dependencies[name] = needed
    if records[GATE]['soname'] != GATE:
        raise Blocked('Guest gate DSO has no proper SONAME')
    # The runtime SDK builds its own gate during compilation. Validate that
    # artifact too, although only the guest-provided gate is staged in the ZIP.
    local_gate = ensure_elf(runtime_gate)
    for name in (GAME, RUNTIME, GPU):
        if GATE not in dependencies[name]:
            raise Blocked('Guest/runtime/GPU missing shared gate DT_NEEDED: ' + name)
    # Ensure not just the gate, but ALL non-system DT_NEEDED deps are present.
    for name, needed in dependencies.items():
        absent = needed - SYSTEM - set(libraries)
        if absent:
            raise Blocked('Unresolved native dependency in ' + name + ': ' + ','.join(sorted(absent)))
    if not set(GATE_SYMBOLS) <= exported(libraries[GATE], readelf):
        raise Blocked('Guest-shared Memgate71 gate ABI exports missing')
    if not set(GATE_SYMBOLS) <= exported(runtime_gate, readelf):
        raise Blocked('Freshly compiled runtime gate ABI exports missing')
    if dynamic(runtime_gate, readelf)[1] != GATE:
        raise Blocked('Freshly compiled runtime gate SONAME mismatch')
    if not {'rex_gpu_abi_version', 'rex_gpu_create'} <= exported(libraries[GPU], readelf):
        raise Blocked('GPU plugin ABI entrypoint missing')
    if 'SDL_main' not in exported(libraries[GAME], readelf) | exported(libraries[RUNTIME], readelf):
        raise Blocked('Android SDL_main symbol absent')
    # Preserve the previous real ABI59 validation for ReXGlue C++ imports.
    symbols = {name: read_dynsym(readelf, libraries[name])
               for name in (GAME, RUNTIME, GPU, CXX)}
    abi59 = check_symbols(symbols)
    records[GATE]['runtime_build_gate_sha256'] = local_gate['sha256']
    records[GATE]['runtime_build_gate_is_same_bytes'] = (
        local_gate['sha256'] == records[GATE]['sha256'])
    return records, abi59


def package(guest: Path, gate: Path, gpu: Path, runtime_dir: Path,
            runtime_report: Path, plume_report: Path, shader_report: Path,
            output: Path, readelf: str) -> dict:
    if output.exists() or output.suffix != '.zip':
        raise Blocked('Output ZIP already exists or invalid name; refuse overwrite')
    evidence = check_evidence(load_json(runtime_report), load_json(plume_report),
                              load_json(shader_report))
    staged = inventory(runtime_dir, guest, gate, gpu)
    records, abi59 = audit(staged, runtime_dir / GATE, readelf)
    report = {
        'stage': 73, 'status': 'ARM64_GUEST_RUNTIME_GPU_GATE_LINKAGE_ONLY',
        'sdk_pin': PIN, 'libraries': records, 'evidence': evidence,
        'resolved_rex_cpp_imports': abi59,
        'single_gate_in_private_bundle': True,
        'guest_runtime_gpu_share_soname': True,
        'guest_global_exclusion_certified': False,
        'device_dma_completion_certified': False,
        'vulkan_queue_fence_completion_certified': False,
        'memexport_commit_permitted': False,
        'production_binary_approved': False,
        'apk_generated': False,
        'warning': ('One gate SONAME and validated linker dependencies are NOT '
                    'runtime proof of all writer coverage or Vulkan fence completion.'),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.memgate73-private-', dir=output.parent) as tmp:
        temp = Path(tmp) / output.name
        with ZipFile(temp, 'x', ZIP_DEFLATED, compresslevel=6) as z:
            for name, path in sorted(staged.items()):
                z.write(path, 'lib/arm64-v8a/' + name)
            z.writestr('diagnostic/memgate73.json',
                       json.dumps(report, indent=2, sort_keys=True) + '\n')
            z.writestr('AVISO.txt', 'Memgate73 diagnostico ARM64; nao e APK. '
                       'GPU 583/588; cinco shaders MemExport nao executaveis; '
                       'sem prova de DMA, fences Vulkan ou gameplay. '
                       'Nao redistribuir binarios privados.\n')
        temp.replace(output)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--guest', type=Path, required=True)
    p.add_argument('--guest-gate', type=Path, required=True)
    p.add_argument('--gpu', type=Path, required=True)
    p.add_argument('--runtime-dir', type=Path, required=True)
    p.add_argument('--runtime-report', type=Path, required=True)
    p.add_argument('--plume-report', type=Path, required=True)
    p.add_argument('--shader-report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--readelf', required=True)
    a = p.parse_args()
    try:
        report = package(a.guest, a.guest_gate, a.gpu, a.runtime_dir,
                         a.runtime_report, a.plume_report, a.shader_report,
                         a.output, a.readelf)
    except (Blocked, ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as err:
        print('BLOCKED Memgate73 packaging: ' + str(err), file=sys.stderr)
        return 2
    print(f'PASS: private ARM64 diagnostic ZIP includes {len(report["libraries"])} ELF libraries')
    print('BLOCKED: no global memory certification, Vulkan fence guarantee or MemExport commits')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
