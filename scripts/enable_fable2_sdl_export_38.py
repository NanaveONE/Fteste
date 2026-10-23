#!/usr/bin/env python3
"""Replace the unsafe pipefail-based SDL_main check in the Android build."""
from __future__ import annotations

import argparse
from pathlib import Path

OLD = '''"$readelf_bin" --dyn-syms "$game_so" | grep -Eq 'FUNC +GLOBAL +DEFAULT +[0-9]+ +SDL_main($|[[:space:]])' || {
    echo 'BLOCKED: libfable2.so does not export SDL_main for SDLActivity' >&2; exit 2;
}'''
NEW = '''# Avoid readelf | grep -q under pipefail: a valid SDL_main can trigger
# SIGPIPE in readelf after grep exits early, causing a false build failure.
python3 "$root/scripts/check_fable2_sdl_export_38.py" \\
    --file "$game_so" --readelf "$readelf_bin"'''


def patch(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Missing Android build script: {path}")
    source = path.read_text(encoding="utf-8")
    if NEW in source:
        if OLD in source:
            raise ValueError("Both old and new checks found; review manually")
        return "already applied"
    if source.count(OLD) != 1:
        raise ValueError("Unexpected SDL_main validation code (upstream changed); no edits made")
    path.write_text(source.replace(OLD, NEW, 1), encoding="utf-8")
    return "patched"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-script", type=Path,
                    default=Path("scripts/build_android_native.sh"))
    args = ap.parse_args()
    print("SDL_main verification 38:", patch(args.build_script))


if __name__ == "__main__":
    main()
