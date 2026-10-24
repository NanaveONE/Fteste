#!/usr/bin/env python3
"""Append fail-closed diagnostic Memgate71 target in isolated Android worktree.

Never modifies tracked upstream Fable II sources, private game source or SDK.
The injected block is opt-in CMake and does not affect a normal build.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

MARK = '# FABLE2_MEMGATE71_GUEST_LINK: optional diagnostic shared gate'
BLOCK = '''
# FABLE2_MEMGATE71_GUEST_LINK: optional diagnostic shared gate
if(FABLE2_MEMGATE71_DIAGNOSTIC)
  if(NOT ANDROID OR NOT FABLE2_PRIVATE_CPP_IMPORTED OR
     NOT EXISTS "${FABLE2_MEMGATE71_SOURCE}" OR
     NOT EXISTS "${FABLE2_MEMGATE71_INCLUDE}/fable_memgate71.h")
    message(FATAL_ERROR "Memgate71 requires verified Android guest and shared gate sources")
  endif()
  if(NOT TARGET fable2_memgate71)
    add_library(fable2_memgate71 SHARED "${FABLE2_MEMGATE71_SOURCE}")
    set_target_properties(fable2_memgate71 PROPERTIES OUTPUT_NAME fable2_memgate71
      LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}" CXX_STANDARD 20)
    target_include_directories(fable2_memgate71 PUBLIC "${FABLE2_MEMGATE71_INCLUDE}")
  endif()
  if(NOT TARGET fable_2_recomp OR NOT TARGET fable_2)
    message(FATAL_ERROR "Verified Fable II generated target unavailable")
  endif()
  target_include_directories(fable_2_recomp PRIVATE "${FABLE2_MEMGATE71_INCLUDE}")
  target_compile_definitions(fable_2_recomp PRIVATE FABLE2_MEMGATE71_DIAGNOSTIC=1)
  target_link_libraries(fable_2 PRIVATE fable2_memgate71)
endif()
'''


def install(worktree: Path, *, check: bool = False) -> None:
    # A caller must pass the isolated build/ directory, not a submodule.
    target = worktree.resolve(strict=True) / 'CMakeLists.txt'
    parts = target.parts
    if 'build' not in parts or not target.is_file():
        raise ValueError('Refusing to change CMake outside an isolated build/ worktree')
    source = target.read_text()
    if MARK in source:
        if source.count(MARK) != 1 or not source.endswith(BLOCK):
            raise ValueError('Altered Memgate71 guest CMake hook')
        return
    if check:
        raise ValueError('Memgate71 guest hook not installed')
    if source.count('add_library(fable_2 SHARED ${FABLE2_SOURCES})') != 1:
        raise ValueError('Patched Android Fable guest target not recognized')
    target.write_text(source + BLOCK)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        install(args.worktree, check=args.check)
    except (OSError, ValueError) as exc:
        print('BLOCKED Memgate71 CMake:', exc, file=sys.stderr)
        return 2
    print('PASS: guest build wired to process-wide diagnostic Memgate71 DSO')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
