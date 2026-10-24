#!/usr/bin/env python3
"""Instrument the PINNED ReXGlue SDK checkout for MemExport62 diagnostics.

No code is added to the tracked fork or to private binaries. Does NOT
implement stop-the-world: the existing MemExport55/60/61 commit gate remains
closed until direct PPC/native stores and async producers are covered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PIN = '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b'
HEADER = 'rex/fable_memexport_sdk62.h'
INCLUDE = '#include <rex/fable_memexport_sdk62.h>\n'
MARK = 'FABLE2_MEMEXPORT62_RUNTIME_AUDIT'

SOURCES = {
    'src/system/xthread.cpp': (
        '#include <rex/system/xthread.h>\n',
        'void XThread::Execute() {\n',
        '  // FABLE2_MEMEXPORT62_RUNTIME_AUDIT: complete direct guest dispatch interval.\n'
        '  fable2::memexport62::WriterScope fable62_guest_scope(\n'
        '      fable2::memexport62::WriterPath::GuestExecute);\n',
    ),
    'src/system/xmemory.cpp': (
        '#include <rex/system/xmemory.h>\n',
        None, None,
    ),
}
HELPERS = (
    ('void Memory::Zero(uint32_t address, uint32_t size) {\n',
     '  // FABLE2_MEMEXPORT62_RUNTIME_AUDIT: host memory helper (NOT all writers).\n'
     '  fable2::memexport62::WriterScope fable62_zero_scope(\n'
     '      fable2::memexport62::WriterPath::MemoryZero, size);\n'),
    ('void Memory::Fill(uint32_t address, uint32_t size, uint8_t value) {\n',
     '  // FABLE2_MEMEXPORT62_RUNTIME_AUDIT: host memory helper (NOT all writers).\n'
     '  fable2::memexport62::WriterScope fable62_fill_scope(\n'
     '      fable2::memexport62::WriterPath::MemoryFill, size);\n'),
    ('void Memory::Copy(uint32_t dest, uint32_t src, uint32_t size) {\n',
     '  // FABLE2_MEMEXPORT62_RUNTIME_AUDIT: host memory helper (NOT all writers).\n'
     '  fable2::memexport62::WriterScope fable62_copy_scope(\n'
     '      fable2::memexport62::WriterPath::MemoryCopy, size);\n'),
)


def one(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected one exact pinned SDK anchor, found {text.count(old)}')
    return text.replace(old, new, 1)


def transform(filename: str, source: str) -> str:
    if MARK in source or INCLUDE in source:
        raise ValueError('Refusing modified/partly instrumented pinned SDK: ' + filename)
    if filename not in SOURCES:
        raise ValueError('Unexpected SDK source ' + filename)
    header, entry, body = SOURCES[filename]
    result = one(source, header, header + INCLUDE, filename + ' header')
    if entry:
        result = one(result, entry, entry + body, filename + ' guest entry')
    else:
        for anchor, insert in HELPERS:
            result = one(result, anchor, anchor + insert, filename + ' helper')
    return result


def patch(sdk: Path, root: Path, check: bool) -> dict:
    sdk = sdk.resolve()
    root = root.resolve()
    revision = subprocess.check_output(
        ['git', '-C', str(sdk), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        raise ValueError(f'Wrong SDK revision {revision}; expected {PIN}')
    expected_header = (root / 'port/sdk/fable_memexport_sdk62.h').read_bytes()
    if not expected_header.startswith(b'#pragma once'):
        raise ValueError('Invalid MemExport62 header')
    paths = {name: sdk / name for name in SOURCES}
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError('Missing pinned ReXGlue source: ' + name)
    target = sdk / 'include' / HEADER
    edited = {}
    for name, path in paths.items():
        original = path.read_text()
        if MARK in original:
            # Exact idempotence check against original committed SDK content.
            upstream = subprocess.check_output(['git', '-C', str(sdk), 'show',
                                                f'HEAD:{name}'], text=True)
            result = transform(name, upstream)
            if original != result:
                raise ValueError('Modified MemExport62 instrumentation: ' + name)
        else:
            result = transform(name, original)
            if check:
                raise ValueError('MemExport62 not yet installed: ' + name)
        edited[name] = result
    if check:
        if not target.is_file() or target.read_bytes() != expected_header:
            raise ValueError('MemExport62 runtime header missing or changed')
    else:
        if target.exists() and target.read_bytes() != expected_header:
            raise ValueError('Existing MemExport62 header differs')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected_header)
        for name, body in edited.items():
            paths[name].write_text(body)
    result = {'stage': 62, 'sdk_commit': PIN,
              'globally_exclusive_verified': False,
              'guest_physical_commit_enabled': False,
              'instrumented_paths': list(SOURCES),
              'source_sha256': {name: hashlib.sha256(body.encode()).hexdigest()
                                for name, body in edited.items()},
              'header_sha256': hashlib.sha256(expected_header).hexdigest()}
    print('PASS: MemExport62 SDK guest execution and memory helpers instrumented')
    print('BLOCKED: complete writer coverage and guest exclusion NOT proven')
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sdk', type=Path, required=True)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    try:
        info = patch(args.sdk, args.root, args.check)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(info, indent=2) + '\n')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        ap.exit(2, f'BLOCKED MemExport62: {error}\n')


if __name__ == '__main__':
    main()
