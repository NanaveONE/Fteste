#!/usr/bin/env bash
# Obtain source dependencies for the Fable-specific Xerenge renderer.
# Intended for Linux x86_64 host with clang, cmake, ninja, and Git.
# This does not fetch copyrighted game files or silently reset local repos.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
base="$root/build/deps"
mkdir -p "$base"
command -v git >/dev/null || { echo 'Git not installed' >&2; exit 2; }
get_repo() {
  local url="$1" dest="$2"
  if [[ -d "$dest/.git" ]]; then
    echo "Already present (not modified): $dest"
  elif [[ -e "$dest" ]]; then
    echo "BLOCKED: $dest exists but is not a Git checkout" >&2
    exit 2
  else
    git clone --depth 1 --recurse-submodules "$url" "$dest"
  fi
}
get_repo https://github.com/shipa-2/rexglue-xerenge.git "$base/rexglue-xerenge"
get_repo https://github.com/shipa-2/plume-xerenge.git "$base/plume-xerenge"
get_repo https://github.com/shipa-2/XenosRecomp-xerenge.git "$base/XenosRecomp-xerenge"

echo
cat <<EOF
Source repositories fetched into $base
Build the host utility and translator on Linux x86_64:
  cmake -S external/Xerenge/tools/cxx -B build/deps/xerenge-tools -G Ninja -DCMAKE_BUILD_TYPE=Release
  cmake --build build/deps/xerenge-tools --target dump_xex_image
  cmake -S build/deps/XenosRecomp-xerenge -B build/deps/xenos-build -G Ninja -DCMAKE_BUILD_TYPE=Release
  cmake --build build/deps/xenos-build --target XenosRecomp

Then run scripts/generate_fable_shaders.py using paths to the two host tools.
DO NOT upload game data, generated guest code, or private shader dumps to GitHub.
EOF
