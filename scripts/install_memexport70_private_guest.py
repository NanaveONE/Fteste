#!/usr/bin/env python3
"""Opt-in diagnostic installation of the *verified* MemExport66 C++ wrappers.

Operates ONLY in ignored Fteste/build/ worktrees. Imports have to be the
original, verified private generated C++ from the same ZIP. It compiles no code,
does not replace any public/production library, and grants NO guest RAM writes.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from instrument_memexport66_guest_writes import (
    Blocked, HEADER, _read_archive, prepare,
)

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
SOURCE_INDEX = re.compile(r'\$\{CMAKE_CURRENT_LIST_DIR\}/(fable_2_(?:recomp\.\d+|init|register)\.cpp)')


def _under_build(path: Path) -> Path:
    resolved = path.resolve()
    root = BUILD.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise Blocked('All destination paths must stay in ignored Fteste/build/')
    return resolved


def _snapshot_file(source: str, destination: str) -> str:
    """Copy unchanged sources without assuming os.link exists on Android.

    Hardlink the staged snapshot when supported to avoid another 313 MB copy.
    If the platform lacks hardlinks, make an independent byte-for-byte copy.
    Never fall back for unexpected I/O errors (disk corruption, path errors).
    All transformed C++ files are later atomically replaced, not mutated.
    """
    link = getattr(os, 'link', None)
    if callable(link):
        try:
            link(source, destination)
            return destination
        except OSError as exc:
            if exc.errno not in (errno.ENOSYS, errno.EOPNOTSUPP,
                                 errno.EXDEV, errno.EPERM, errno.EMLINK):
                raise
    return shutil.copy2(source, destination)


def install(archive: Path, generated_dir: Path, report_path: Path, *,
            expected_source_sha256: str | None = None,
            expected_translation_units: int = 297,
            expected_atomics: int = 8436,
            expected_intrinsics: int = 38) -> dict:
    """Preflight ALL files, install into a separate tree, then swap directories.

    A directory swap is recoverable if the second rename fails. A sudden machine
    power loss may still leave an ignored .memexport70-backup-* directory; in
    that case we fail closed rather than silently building mixed sources.
    """
    if generated_dir.is_symlink():
        raise Blocked('Refusing symlinked generated source directory')
    generated_dir = _under_build(generated_dir)
    report_path = _under_build(report_path)
    archive = archive.resolve(strict=True)
    if generated_dir.name != 'default' or generated_dir.parent.name != 'generated':
        raise Blocked('Destination must be a private generated/default directory')
    if report_path == archive:
        raise Blocked('Report must not overwrite the private source ZIP')
    if report_path.is_relative_to(generated_dir):
        raise Blocked('Report must be outside generated/default/')
    if not generated_dir.is_dir() or generated_dir.is_symlink():
        raise Blocked('Original generated/default directory missing or symlinked')
    if not (generated_dir / 'codegen.build.stamp').is_file():
        raise Blocked('Verified private generated import stamp missing')
    if report_path.exists():
        raise Blocked('Report already exists; refusing to mix diagnostic runs')
    if not HEADER.is_file():
        raise Blocked('MemExport66 observer header missing')

    sources, source_hash = _read_archive(archive)
    if len(sources) != expected_translation_units:
        raise Blocked(f'Translation unit mismatch: {len(sources)} vs {expected_translation_units}')
    if expected_source_sha256 and source_hash.lower() != expected_source_sha256.lower():
        raise Blocked('Guest source-set provenance hash differs')
    source_names = {name for name, _ in sources}
    index = (generated_dir / 'sources.cmake')
    if not index.is_file() or index.is_symlink():
        raise Blocked('Missing original generated CMake source index')
    cmake_names = SOURCE_INDEX.findall(index.read_text(encoding='utf-8'))
    if len(cmake_names) != len(source_names) or set(cmake_names) != source_names:
        raise Blocked('Generated source index and private ZIP disagree')
    if any(p.is_symlink() for p in generated_dir.rglob('*')):
        raise Blocked('Symlinks forbidden inside private generated source directory')
    if (generated_dir / HEADER.name).exists():
        raise Blocked('MemExport66 header already present; clean private worktree first')

    # Preflight every file before changing anything in the build worktree.
    for name, expected in sources:
        path = generated_dir / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise Blocked('Private C++ source changed since verified import')
    # A stale backup marks an interrupted transaction: do not assume safety.
    backup = generated_dir.parent / '.memexport70-backup-default'
    if backup.exists() or backup.is_symlink():
        raise Blocked('An earlier diagnostic swap was interrupted; inspect backup')

    parent = generated_dir.parent
    # The diagnostic transformer stores its private transformed sources under
    # Fteste/build/ and checks full provenance/call counts before returning.
    converted = Path(tempfile.mkdtemp(prefix='.memexport70-converted-', dir=BUILD))
    converted.rmdir()  # prepare() requires a non-existent output directory.
    shadow = Path(tempfile.mkdtemp(prefix='.memexport70-shadow-', dir=parent))
    shadow.rmdir()
    original_moved = False
    shadow_installed = False
    try:
        result = prepare(archive, converted, BUILD / 'memexport70-transformed-tmp-report.json',
                         expect_source_hash=expected_source_sha256,
                         expect_atomics=expected_atomics,
                         expect_intrinsics=expected_intrinsics)
        if result['translation_units'] != expected_translation_units:
            raise Blocked('Transformed inventory changed unexpectedly')
        if (result['counters']['direct_guest_store_candidates_uncovered'] != 0):
            raise Blocked('Known direct guest stores remain uncovered')

        # Snapshot in the ignored private worktree. Use hardlinks if supported,
        # otherwise independently copy unchanged files (Termux may lack os.link).
        # Changed C++ files are always replaced, never edited via hardlink.
        shutil.copytree(generated_dir, shadow, copy_function=_snapshot_file,
                        symlinks=False)
        for name in source_names:
            os.replace(converted / name, shadow / name)
        shutil.copy2(converted / HEADER.name, shadow / HEADER.name)
        if len(list(shadow.glob('fable_2_*.cpp'))) != len(source_names):
            raise Blocked('Staged generated source inventory differs')
        for name in source_names:
            if not (shadow / name).is_file() or (shadow / name).is_symlink():
                raise Blocked('Staged transformed source missing')

        # Swap the whole generated/default folder with rollback on ordinary IO
        # errors, so CMake cannot see a partially transformed source set.
        generated_dir.rename(backup)
        original_moved = True
        shadow.rename(generated_dir)
        shadow_installed = True
        result70 = {
            'stage': 70,
            'status': 'PRIVATE_GUEST_ARM64_DIAGNOSTIC_INSTRUMENTATION_ONLY',
            'translation_units': expected_translation_units,
            'original_source_set_sha256': source_hash,
            'instrumented_source_set_sha256': result['instrumented_source_set_sha256'],
            'atomic_calls_wrapped': result['counters']['atomic_calls_wrapped'],
            'memory_intrinsics_wrapped': result['counters']['memory_intrinsics_wrapped'],
            'guest_global_exclusion_certified': False,
            'memexport_commit_permitted': False,
            'production_binary_approved': False,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result70, indent=2) + '\n')
        # Only after the verified report exists can the original source snapshot
        # be deleted. This is the ignored build clone, NEVER the private ZIP.
        shutil.rmtree(backup)
        original_moved = False
        return result70
    except Exception:
        if original_moved and backup.exists():
            if shadow_installed and generated_dir.exists():
                shutil.rmtree(generated_dir)
            backup.rename(generated_dir)
        raise
    finally:
        shutil.rmtree(shadow, ignore_errors=True)
        shutil.rmtree(converted, ignore_errors=True)
        (BUILD / 'memexport70-transformed-tmp-report.json').unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', required=True, type=Path)
    p.add_argument('--generated-dir', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--expected-source-sha256')
    p.add_argument('--expected-translation-units', type=int, default=297)
    p.add_argument('--expected-atomics', type=int, default=8436)
    p.add_argument('--expected-intrinsics', type=int, default=38)
    a = p.parse_args()
    try:
        result = install(a.archive, a.generated_dir, a.report,
                         expected_source_sha256=a.expected_source_sha256,
                         expected_translation_units=a.expected_translation_units,
                         expected_atomics=a.expected_atomics,
                         expected_intrinsics=a.expected_intrinsics)
    except (OSError, ValueError, Blocked) as exc:
        print('BLOCKED MemExport70: ' + str(exc), file=sys.stderr)
        return 2
    print('PASS: private guest source tree instrumented for diagnostic ARM64 build')
    print('BLOCKED: no global guest CPU/GPU exclusion proof; MemExport RAM commits disabled')
    print(json.dumps({'files': result['translation_units'],
                      'atomics': result['atomic_calls_wrapped'],
                      'intrinsics': result['memory_intrinsics_wrapped']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
