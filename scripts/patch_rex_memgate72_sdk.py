#!/usr/bin/env python3
"""Memgate72: opt-in known *actual* GPU/host RAM write and mapping scopes.

Patches only a verified pinned ReXGlue build/ clone after Memgate71. Physical
DMA, unenumerated producers, device completion and cache correctness are NOT
certified. No guest-RAM GPU commit becomes permitted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PIN = '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b'
MARK = 'FABLE2_MEMGATE72_RUNTIME_HOOK'
INCLUDE = '#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n#include "fable_memgate71.h"\n#endif\n// ' + MARK + '\n'

# Scope just the actual CPU store, not the GPU's whole continuously-running
# worker thread. Pending GPU submissions are NOT guaranteed to be finished.
COMMAND = (
    ('memory::store_and_swap<uint32_t>(memory_->TranslatePhysical(read_ptr_writeback_ptr_),\n'
     '                                       read_ptr_index_);', 'FABLE_M71_GPU_PRODUCER', 'read_ptr_writeback'),
    ('memory::store_and_swap<uint32_t>(memory_->TranslatePhysical(mem_addr), value);',
     'FABLE_M71_GPU_PRODUCER', 'scratch_register_writeback'),
    ('memory::store(memory_->TranslatePhysical(mem_addr), reg_val);',
     'FABLE_M71_DMA_MAPPING', 'reg_to_mem'),
    ('memory::store(memory_->TranslatePhysical(addr), write_data);',
     'FABLE_M71_DMA_MAPPING', 'mem_write'),
    ('memory::store(memory_->TranslatePhysical(write_reg_addr), write_data);',
     'FABLE_M71_DMA_MAPPING', 'cond_write'),
    ('memory::store(memory_->TranslatePhysical(address), data_value);',
     'FABLE_M71_DMA_MAPPING', 'event_write_shd'),
    ('memory::copy_and_swap_16_unaligned(memory_->TranslatePhysical(address), extents,\n'
     '                                     rex::countof(extents));',
     'FABLE_M71_DMA_MAPPING', 'event_write_ext'),
)

# This packet writes through a struct pointer (memset plus fields). Keep the
# entire short handler in the writer scope, including post-memset stores.
COMMAND_FUNCTIONS = (
    ('bool CommandProcessor::ExecutePacketType3_EVENT_WRITE_ZPD(memory::RingBuffer* reader,\n'
     '                                                          uint32_t packet, uint32_t count) {\n',
     'FABLE_M71_DMA_MAPPING', 'event_write_zpd'),
)

# Guest mapping is a separate category. The scope is taken before SDK locks;
# this still does not prove all VM operations or asynchronous DMA participate.
MEMORY_FUNCTIONS = (
    # The pinned xmemory.cpp has a 260-byte multi-line signature. Match the
    # ENTIRE header, including the opening brace, rather than guessing where
    # the body begins with a 230-character lookahead.
    ('bool Memory::AddVirtualMappedRange(uint32_t virtual_address, uint32_t mask, uint32_t size,\n'
     '                                   void* context, runtime::MMIOReadCallback read_callback,\n'
     '                                   runtime::MMIOWriteCallback write_callback) {\n',
     'FABLE_M71_DMA_MAPPING', 'mapped_range'),
    ('uint32_t Memory::SystemHeapAlloc(uint32_t size, uint32_t alignment, uint32_t system_heap_flags) {\n',
     'FABLE_M71_DMA_MAPPING', 'system_heap_alloc'),
    ('void Memory::SystemHeapFree(uint32_t address, uint32_t* out_region_size) {\n',
     'FABLE_M71_DMA_MAPPING', 'system_heap_free'),
)

# RangeWrittenByGpu is a notification of GPU results; NOT proof that the GPU
# work is complete. The scope only protects this CPU-side notification.
SHARED_FUNCTIONS = (
    ('void SharedMemory::RangeWrittenByGpu(uint32_t start, uint32_t length) {\n',
     'FABLE_M71_GPU_PRODUCER', 'gpu_range_notification'),
)

FILES = ('src/graphics/command_processor.cpp', 'src/system/xmemory.cpp',
         'src/graphics/shared_memory.cpp')


def _one(content: str, needle: str, replacement: str, what: str) -> str:
    hits = content.count(needle)
    if hits != 1:
        raise ValueError(f'Pinned SDK hook {what}: expected one anchor, found {hits}')
    return content.replace(needle, replacement, 1)


def _function(content: str, signature: str, kind: str, label: str) -> str:
    # Every pinned signature ends at the function's opening brace. An exact,
    # unique match prevents injection into the wrong function if SDK drifts.
    if not signature.endswith(' {\n'):
        raise ValueError('Pinned function signature lacks opening brace: ' + label)
    return _one(content, signature, signature + _guard(kind, label), label)



def _guard(kind: str, label: str) -> str:
    return ('#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n'
            f'  fable2::memgate71::WriterScope fable72_{label}({kind});\n'
            '#endif\n')


def _call_scope(old: str, kind: str, label: str) -> str:
    # Exact one-call scope; NEVER hold a lease for the entire idle GPU loop.
    return '{\n' + _guard(kind, label) + old + '\n}'


def _validate_installed(name: str, content: str) -> None:
    """Require every exact hook and reverse the installation to its base.

    This verifies our changes, not every independent upstream/SDK edit.
    """
    if content.count(MARK) != 1:
        raise ValueError('Missing/duplicated Memgate72 source marker')
    restored = content
    if name == FILES[0]:
        for old, kind, label in COMMAND:
            restored = _one(restored, _call_scope(old, kind, label), old, label)
        groups = COMMAND_FUNCTIONS
    elif name == FILES[1]:
        groups = MEMORY_FUNCTIONS
    elif name == FILES[2]:
        groups = SHARED_FUNCTIONS
    else:
        raise ValueError('Unexpected installed source')
    for signature, kind, label in groups:
        # The injected guard always immediately follows the function '{'.
        if not signature.endswith(' {\n') or restored.count(signature) != 1:
            raise ValueError('Installed scope function anchor missing or drifted: '+label)
        where = restored.index(signature) + len(signature)
        guard = _guard(kind, label)
        if not restored.startswith(guard, where):
            raise ValueError('Installed scope is absent/moved: '+label)
        restored = restored[:where] + restored[where+len(guard):]
    # Include is inserted right after an exact SDK header line.
    header = {'src/graphics/command_processor.cpp': '#include <rex/graphics/command_processor.h>\n',
              'src/system/xmemory.cpp': '#include <rex/system/xmemory.h>\n',
              'src/graphics/shared_memory.cpp': '#include <rex/graphics/shared_memory.h>\n'}[name]
    restored = _one(restored, header + INCLUDE, header, name + ' header')
    if modify(name, restored) != content:
        raise ValueError('Memgate72 reversible install validation failed')

def modify(name: str, content: str) -> str:
    if name not in FILES:
        raise ValueError('Unrecognized SDK source')
    if MARK in content:
        raise ValueError('Memgate72 duplicate or partial installation')
    # Memgate71 C++ runtime headers are already included by other sources;
    # include guard avoids conflicts in xmemory.cpp.
    if name == FILES[0]:
        header = '#include <rex/graphics/command_processor.h>\n'
    elif name == FILES[1]:
        header = '#include <rex/system/xmemory.h>\n'
    else:
        header = '#include <rex/graphics/shared_memory.h>\n'
    content = _one(content, header, header + INCLUDE, name + ' header')
    if name == FILES[0]:
        for token, kind, label in COMMAND:
            content = _one(content, token, _call_scope(token, kind, label), label)
        for sig, kind, label in COMMAND_FUNCTIONS:
            content = _function(content, sig, kind, label)
    elif name == FILES[1]:
        for sig, kind, label in MEMORY_FUNCTIONS:
            content = _function(content, sig, kind, label)
    else:
        for sig, kind, label in SHARED_FUNCTIONS:
            content = _function(content, sig, kind, label)
    return content


def _preflight(sdk: Path) -> tuple[dict[str, Path], dict[str, str]]:
    sdk = sdk.resolve(strict=True)
    pin = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'],
                                  text=True).strip()
    if pin != PIN:
        raise ValueError('Pinned ReXGlue revision drift')
    files = {p: sdk / p for p in FILES}
    if any(not p.is_file() or p.is_symlink() for p in files.values()):
        raise ValueError('Required pinned SDK source missing/symlinked')
    originals = {n: p.read_text() for n, p in files.items()}
    return files, originals


def patch(sdk: Path, *, check: bool = False) -> dict:
    files, original = _preflight(sdk)
    if check:
        if not all(MARK in body for body in original.values()):
            raise ValueError('Memgate72 SDK hooks missing')
        for name, body in original.items():
            _validate_installed(name, body)
        return {'sdk_pin': PIN, 'source_files': len(FILES),
                'scope_sites': len(COMMAND)+len(COMMAND_FUNCTIONS)+len(MEMORY_FUNCTIONS)+len(SHARED_FUNCTIONS),
                'commit_permitted': False}
    if any(MARK in body for body in original.values()):
        raise ValueError('Stale/partial Memgate72 SDK instrumentation; refuse double install')
    # Stage71 must be installed first to ensure all three CMake targets link
    # the process-wide shared coordinator.
    if 'FABLE2_MEMGATE71_SHARED_RUNTIME' not in (sdk/'CMakeLists.txt').read_text():
        raise ValueError('Memgate71 shared runtime CMake hook missing')
    if not all('FABLE2_MEMGATE71_COOPERATIVE_SCOPE' in original[p]
               for p in ('src/system/xmemory.cpp',)):
        raise ValueError('Memgate71 SDK memory hooks missing')
    edited = {name: modify(name, body) for name, body in original.items()}
    for name, path in files.items():
        path.write_text(edited[name])
    return {'sdk_pin': PIN, 'source_files': len(FILES),
            'scope_sites': len(COMMAND)+len(COMMAND_FUNCTIONS)+len(MEMORY_FUNCTIONS)+len(SHARED_FUNCTIONS),
            'sha256': {n: hashlib.sha256(v.encode()).hexdigest() for n,v in edited.items()},
            'commit_permitted': False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sdk', required=True, type=Path)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    try:
        report = patch(args.sdk, check=args.check)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('BLOCKED Memgate72 SDK:', exc, file=sys.stderr)
        return 2
    print('PASS: known ReXGlue GPU stores/mapping hooks enrolled (diagnostic only)')
    print('BLOCKED: device DMA and MemExport GPU RAM commits remain unverified')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
