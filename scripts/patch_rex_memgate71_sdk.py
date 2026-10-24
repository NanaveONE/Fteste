#!/usr/bin/env python3
"""Opt-in MemExport71 pinned-SDK guest/runtime scope installation (diagnostic)."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

PIN = '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b'
MARK = 'FABLE2_MEMGATE71_COOPERATIVE_SCOPE'
INC = '#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n#include "fable_memgate71.h"\n#endif\n'
SITES = {
    'src/system/xthread.cpp': (
        '#include <rex/system/xthread.h>\n',
        ('void XThread::Execute() {\n', '  fable2::memgate71::WriterScope fable71_guest(FABLE_M71_GUEST_THREAD);\n'),
    ),
    'src/system/xmemory.cpp': (
        '#include <rex/system/xmemory.h>\n',
        ('void Memory::Zero(uint32_t address, uint32_t size) {\n', '  fable2::memgate71::WriterScope fable71_zero(FABLE_M71_RUNTIME_HELPER);\n'),
        ('void Memory::Fill(uint32_t address, uint32_t size, uint8_t value) {\n', '  fable2::memgate71::WriterScope fable71_fill(FABLE_M71_RUNTIME_HELPER);\n'),
        ('void Memory::Copy(uint32_t dest, uint32_t src, uint32_t size) {\n', '  fable2::memgate71::WriterScope fable71_copy(FABLE_M71_RUNTIME_HELPER);\n'),
    ),
}
SDK_CMAKE = '''
# FABLE2_MEMGATE71_SHARED_RUNTIME: process-wide diagnostic-only participant.
if(FABLE2_MEMGATE71_DIAGNOSTIC)
  if(NOT EXISTS "${FABLE2_MEMGATE71_SOURCE}" OR
     NOT EXISTS "${FABLE2_MEMGATE71_INCLUDE}/fable_memgate71.h")
    message(FATAL_ERROR "Missing source/headers for diagnostic Memgate71")
  endif()
  if(NOT TARGET fable2_memgate71)
    add_library(fable2_memgate71 SHARED "${FABLE2_MEMGATE71_SOURCE}")
    set_target_properties(fable2_memgate71 PROPERTIES
      OUTPUT_NAME fable2_memgate71
      LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
      CXX_STANDARD 20 POSITION_INDEPENDENT_CODE ON)
    target_include_directories(fable2_memgate71 PUBLIC "${FABLE2_MEMGATE71_INCLUDE}")
  endif()
  if(NOT TARGET rexruntime)
    message(FATAL_ERROR "Pinned ReXGlue no longer has rexruntime target")
  endif()
  target_include_directories(rexruntime PRIVATE "${FABLE2_MEMGATE71_INCLUDE}")
  target_compile_definitions(rexruntime PRIVATE FABLE2_MEMGATE71_DIAGNOSTIC=1)
  target_link_libraries(rexruntime PRIVATE fable2_memgate71)
endif()
'''


def modify(name: str, content: str) -> str:
    if name not in SITES or MARK in content:
        raise ValueError('Already or unexpectedly instrumented SDK source')
    include, *sites = SITES[name]
    if content.count(include) != 1:
        raise ValueError('Pinned SDK header anchor drift: ' + name)
    content = content.replace(include, include + INC + '// ' + MARK + '\n', 1)
    for anchor, scope in sites:
        if content.count(anchor) != 1:
            raise ValueError('Pinned SDK scope anchor drift: ' + name)
        content = content.replace(anchor, anchor + '#if defined(FABLE2_MEMGATE71_DIAGNOSTIC)\n' + scope + '#endif\n', 1)
    return content


def patch(sdk: Path, *, check: bool = False) -> dict:
    sdk = sdk.resolve(strict=True)
    revision = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'],
                                       text=True).strip()
    if revision != PIN:
        raise ValueError('ReXGlue revision mismatch; fail closed')
    paths = {p: sdk / p for p in SITES}
    cmake = sdk / 'CMakeLists.txt'
    if not cmake.is_file() or not all(p.is_file() for p in paths.values()):
        raise ValueError('Required pinned SDK sources missing')
    if check:
        if SDK_CMAKE.strip() not in cmake.read_text():
            raise ValueError('SDK diagnostic CMake hook missing')
        if not all(MARK in p.read_text() for p in paths.values()):
            raise ValueError('SDK scope hooks missing')
        return {'sdk_pin': PIN, 'scope_sites': 4, 'commit_enabled': False}
    # Validate ALL sources before writing to avoid known partial installations.
    originals = {n: p.read_text() for n, p in paths.items()}
    if any(MARK in body for body in originals.values()) or 'FABLE2_MEMGATE71_SHARED_RUNTIME' in cmake.read_text():
        raise ValueError('Stale Memgate71 SDK instrumentation; refuse double install')
    modified = {n: modify(n, body) for n, body in originals.items()}
    for n, p in paths.items():
        p.write_text(modified[n])
    with cmake.open('a') as out:
        out.write(SDK_CMAKE)
    return {'sdk_pin': PIN, 'scope_sites': 4, 'commit_enabled': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        report = patch(args.sdk, check=args.check)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('BLOCKED Memgate71 SDK: ' + str(exc), file=sys.stderr)
        return 2
    print('PASS Memgate71 SDK scopes:', report)
    print('BLOCKED: all-writer certification and GPU memory commits')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
