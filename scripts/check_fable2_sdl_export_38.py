#!/usr/bin/env python3
"""Verify that a linked Android Fable II ELF exports a usable SDL_main.

Use subprocess.run to consume the whole symbol table. In particular, never
combine `readelf | grep -q` with bash pipefail: early grep exit sends SIGPIPE
back to readelf, turning a matching export into a false build failure.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# GNU-style llvm-readelf --dyn-syms columns:
# Num: Value Size Type Bind Vis Ndx Name
# Accept only *defined*, globally visible functions named exactly SDL_main.
EXPORTED_ENTRY = re.compile(
    r"^\s*\d+:\s+\S+\s+\S+\s+FUNC\s+GLOBAL\s+DEFAULT\s+"
    r"(?!UND\b)\S+\s+SDL_main\s*$",
    re.MULTILINE,
)


def check(file: Path, readelf: Path) -> tuple[bool, str]:
    if not file.is_file() or file.stat().st_size == 0:
        return False, f"BLOCKED: missing or empty linked library: {file}"
    if not readelf.is_file():
        return False, f"BLOCKED: llvm-readelf is missing: {readelf}"
    try:
        result = subprocess.run(
            [str(readelf), "--dyn-syms", "--wide", str(file)],
            capture_output=True, text=True, errors="replace", check=False,
        )
    except OSError as exc:
        return False, f"BLOCKED: cannot run llvm-readelf: {exc}"
    if result.returncode:
        return False, (f"BLOCKED: llvm-readelf exited {result.returncode}: "
                       f"{result.stderr[-2000:]}")
    if EXPORTED_ENTRY.search(result.stdout):
        return True, "PASS: libfable2.so exports a defined GLOBAL DEFAULT SDL_main"
    candidates = [line.strip() for line in result.stdout.splitlines()
                  if re.search(r"\bSDL_main\b", line)]
    detail = "\n  ".join(candidates[:12]) if candidates else "no SDL_main symbol in dynamic table"
    return False, ("BLOCKED: libfable2.so has no exported, defined SDL_main for SDLActivity. "
                   "Related dynamic symbols:\n  " + detail + "\n"
                   "Check __ANDROID__/REX_PLATFORM_ANDROID, hidden visibility, "
                   "and src/ui/windowed_app_main_sdl.cpp; do not bypass this check.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--readelf", required=True, type=Path)
    args = ap.parse_args()
    ok, message = check(args.file, args.readelf)
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
