#!/usr/bin/env python3
"""Prepare a *local* Fable II Android CMake overlay; never mutate submodules.

This does NOT produce a working native game: a compatible ReXGlue SDK,
recompiled guest code, the Fable-specific Vulkan backend, and platform
adaptations remain necessary. It converts the real Fable II CMake target
from a desktop executable to the Android .so needed by SDLActivity.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ORIGINAL = """if(WIN32)
    add_executable(fable_2 WIN32 ${FABLE2_SOURCES})
else()
    add_executable(fable_2 ${FABLE2_SOURCES})
endif()"""

REPLACEMENT = """if(ANDROID)
    # Native game library loaded by port/android/Fable2Activity.java.
    # Requires an Android-compatible ReXGlue runtime and renderer.
    add_library(fable_2 SHARED ${FABLE2_SOURCES})
    set_target_properties(fable_2 PROPERTIES OUTPUT_NAME fable2)
elseif(WIN32)
    add_executable(fable_2 WIN32 ${FABLE2_SOURCES})
else()
    add_executable(fable_2 ${FABLE2_SOURCES})
endif()"""


def replace_target(content: str) -> str:
    count = content.count(ORIGINAL)
    if count != 1:
        raise ValueError(f"Expected exactly one desktop target block, found {count}; inspect upstream changes")
    return content.replace(ORIGINAL, REPLACEMENT)


def excluded(_directory: str, names: list[str]) -> set[str]:
    """Do not copy VCS state, huge content or local build outputs."""
    prohibited = {".git", "data", "out", "build", "build-android", ".vs", "cache", "saves", "logs"}
    extensions = (".iso", ".xex", ".god", ".apk", ".aab")
    return {name for name in names if name in prohibited or name.lower().endswith(extensions)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("external/Fable-2-Recomp"))
    parser.add_argument("--output", type=Path, default=Path("build/fable2-android-worktree"))
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    cmake = source / "CMakeLists.txt"
    if not cmake.is_file():
        parser.error("Fable-2-Recomp absent; run git submodule update --init")
    try:
        # Check before copying anything, so a changed upstream layout fails safely.
        patched = replace_target(cmake.read_text(encoding="utf-8"))
    except ValueError as error:
        parser.error(str(error))
    if output.exists():
        parser.error(f"Refusing to overwrite existing output: {output}")
    if source == output or source in output.parents or output in source.parents:
        parser.error("Output must be separate from the original Fable II submodule")
    shutil.copytree(source, output, ignore=excluded, symlinks=False)
    (output / "CMakeLists.txt").write_text(patched, encoding="utf-8")
    print(f"[OK] Prepared Android shared-library CMake target in {output}")
    print("[PENDING] This is not a compiled game: GPU backend, SDK, SDL_main, game codegen and Android hooks remain.")
    print("[PENDING] No commercial game data was included. Do not commit build/ to GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
