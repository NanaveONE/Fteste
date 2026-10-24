#!/usr/bin/env python3
"""Memgate72: layer real Plume producer/PM4 hooks over verified overlay61.

Only in ignored build/, never mutates the Xerenge checkout, GPU completion
fences, original shader assets or guest RAM. Requires explicit CMake opt-in.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

MARK = '// FABLE2_MEMGATE72_PLUME_REAL_PATHS'
HEADER = '#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n#include "fable_memgate71.h"\n#endif\n' + MARK + '\n'
GRAPHICS_METHODS = (
    ('void PlumeGraphicsSystem::Pm4WritePhysical(uint32_t phys_addr, uint32_t value) {\n',
     'FABLE_M71_DMA_MAPPING', 'pm4_physical_write'),
    ('void PlumeGraphicsSystem::WriteReadPointerWriteback() {\n',
     'FABLE_M71_GPU_PRODUCER', 'read_pointer_writeback'),
    ('bool PlumeGraphicsSystem::ExecutePm4Buffer(uint32_t base_phys, uint32_t start_index,\n'
     '                                           uint32_t end_index, uint32_t wrap_mask, bool wrapping,\n'
     '                                           int depth) {\n',
     'FABLE_M71_GPU_PRODUCER', 'pm4_execute'),
    ('void PlumeGraphicsSystem::NoteGuestResolve(uint32_t flags, uint32_t dest_physical,\n'
     '                                           uint32_t source_width, uint32_t source_height,\n'
     '                                           uint32_t face, bool cube) {\n',
     'FABLE_M71_GPU_PRODUCER', 'resolve_request'),
)
DRAW_METHODS = (
    ('void PlumeDrawContext::ResolveRenderTarget(plume::RenderCommandList* list,\n'
     '                                           plume::RenderTexture* color, uint32_t width,\n'
     '                                           uint32_t height, uint32_t dest_base,\n'
     '                                           uint32_t dest_width, uint32_t dest_height,\n'
     '                                           uint32_t region_width, uint32_t region_height,\n'
     '                                           uint32_t face, bool cube, bool zero) {\n',
     'FABLE_M71_GPU_PRODUCER', 'resolve_encoding'),
)

# This includes submitted host work only, not completion of asynchronous Vulkan
# commands; those require an actual queue fence and device ownership protocol.
GRAPHICS_CALLS = (
    ('if (!CaptureGuestVideoFrame(&request, memory_)) {', 'gpu_capture_read'),
    ('PresentClearColorOnUiThread(w, h);', 'present_worker'),
)
FILES = ('plume_graphics_system.cpp', 'plume_draw.cpp')


def one(content: str, old: str, new: str, label: str) -> str:
    if content.count(old) != 1:
        raise ValueError(f'Plume72 {label} anchor drift: {content.count(old)}')
    return content.replace(old, new, 1)


def scope(anchor: str, kind: str, label: str) -> str:
    return (anchor + '#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n'
            f'  fable2::memgate71::WriterScope fable72_{label}({kind});\n'
            '#endif\n')


def transform(name: str, text: str) -> str:
    if name not in FILES or MARK in text:
        raise ValueError('Unexpected/already instrumented Plume72 source')
    # Prepend only to isolated overlay; original upstream includes are untouched.
    text = HEADER + text
    if name == FILES[0]:
        for anchor, kind, label in GRAPHICS_METHODS:
            text = one(text, anchor, scope(anchor, kind, label), label)
        for original, label in GRAPHICS_CALLS:
            kind = 'FABLE_M71_GPU_PRODUCER'
            if label == 'gpu_capture_read':
                # Lambda spans precisely the guest frame read; no request
                # mutex is held at this point in the video worker.
                patched = (f'if (!([&]() {{\n#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n'
                           f'  fable2::memgate71::WriterScope fable72_{label}({kind});\n'
                           '#endif\n  return CaptureGuestVideoFrame(&request, memory_);\n})()) {')
            else:
                patched = ('{\n#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n'
                           f'  fable2::memgate71::WriterScope fable72_{label}({kind});\n'
                           '#endif\n  PresentClearColorOnUiThread(w, h);\n}')
            text = one(text, original, patched, label)
    else:
        for anchor, kind, label in DRAW_METHODS:
            text = one(text, anchor, scope(anchor, kind, label), label)
    return text


def checksum(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def prepare(base: Path, dest: Path, *, check: bool = False) -> dict:
    base, dest = base.resolve(strict=True), dest.resolve()
    if (base == dest or base in dest.parents or dest in base.parents
            or 'build' not in dest.parts or 'build' not in base.parts):
        raise ValueError('Overlay72 must remain a separate ignored build/ layer')
    if not all((base / f).is_file() and not (base / f).is_symlink() for f in FILES):
        raise ValueError('Verified Plume61 source absent or symlinked')
    if not (base / 'plume61-manifest.json').is_file():
        raise ValueError('Verified MemExport61 overlay manifest missing')
    old = {name: (base/name).read_text(encoding='utf-8') for name in FILES}
    new = {name: transform(name, old[name]).encode('utf-8') for name in FILES}
    report = {
        'stage': 72,
        'status': 'PLUME_KNOWN_CPU_PATHS_ONLY_NOT_CERTIFIED',
        'source': {name: checksum(old[name].encode('utf-8')) for name in FILES},
        'transformed': {name: checksum(new[name]) for name in FILES},
        'registered_scope_sites': len(GRAPHICS_METHODS)+len(DRAW_METHODS)+len(GRAPHICS_CALLS),
        'vulkan_device_completion_covered': False,
        'all_dma_paths_covered': False,
        'memexport_commit_permitted': False,
    }
    if dest.exists():
        if not dest.is_dir():
            raise ValueError('Overlay72 destination is not a directory')
        if not (dest/'plume72-manifest.json').is_file():
            raise ValueError('Existing overlay72 missing manifest')
        if json.loads((dest/'plume72-manifest.json').read_text()) != report:
            raise ValueError('Existing overlay72 manifest mismatch')
        if any(not (dest/name).is_file() or (dest/name).read_bytes() != new[name] for name in FILES):
            raise ValueError('Existing overlay72 source drift')
        return report
    if check:
        raise ValueError('Overlay72 not installed')
    dest.mkdir(parents=True)
    try:
        for name, body in new.items():
            (dest/name).write_bytes(body)
        # Unmodified overlay61 headers are copied (not symlinked) into layer72.
        for name in ('plume_renderer/plume_draw.h',):
            target = dest/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((base/name).read_bytes())
        (dest/'plume72-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    except Exception:
        import shutil
        shutil.rmtree(dest)
        raise
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-overlay', required=True, type=Path)
    p.add_argument('--overlay', required=True, type=Path)
    p.add_argument('--check', action='store_true')
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    try:
        r = prepare(a.base_overlay, a.overlay, check=a.check)
        if a.report:
            a.report.parent.mkdir(parents=True, exist_ok=True)
            a.report.write_text(json.dumps(r, indent=2) + '\n')
    except (OSError, ValueError) as e:
        print('BLOCKED Memgate72 Plume:', e, file=sys.stderr)
        return 2
    print('PASS: Plume72 producer and physical-RAM write scopes installed')
    print('BLOCKED: Vulkan queue completion, DMA and guest GPU commits still unverified')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
