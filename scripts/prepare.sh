#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$HOME/Fable2-Android-Xerenge}"
mkdir -p "$ROOT/upstream" "$ROOT/bridge" "$ROOT/notes"

fetch_repo() {
  local url="$1" path="$2"
  if [ -d "$path/.git" ]; then
    echo "[OK] Repo existente: $path (nao alterado)"
  elif [ -e "$path" ]; then
    echo "[ERRO] $path ja existe e nao eh um checkout git. Interrompendo." >&2
    exit 1
  else
    git clone --filter=blob:none "$url" "$path"
  fi
}

fetch_repo 'https://github.com/shipa-2/Xerenge.git' "$ROOT/upstream/Xerenge"
fetch_repo 'https://github.com/himdo/Fable-2-Recomp.git' "$ROOT/upstream/Fable-2-Recomp"

# Copiar so a integracao Android para analise. Nao mudar os repos originais.
mkdir -p "$ROOT/bridge/xerenge-reference"
cp -R "$ROOT/upstream/Xerenge/rexglue/android" "$ROOT/bridge/xerenge-reference/"
cp "$ROOT/upstream/Xerenge/rexglue/src/android_touch.cpp" "$ROOT/bridge/xerenge-reference/"
cp "$ROOT/upstream/Xerenge/rexglue/src/android_vibration.cpp" "$ROOT/bridge/xerenge-reference/"
cp "$ROOT/upstream/Xerenge/rexglue/CMakeLists.txt" "$ROOT/bridge/xerenge-reference/CMakeLists.txt.reference"
cp "$ROOT/upstream/Fable-2-Recomp/fable_2_manifest.toml" "$ROOT/bridge/fable_2_manifest.toml.reference"
cp "$ROOT/upstream/Fable-2-Recomp/CMakeLists.txt" "$ROOT/bridge/Fable2.CMakeLists.txt.reference"

printf 'Xerenge: ' > "$ROOT/notes/upstream-revisions.txt"
git -C "$ROOT/upstream/Xerenge" rev-parse HEAD >> "$ROOT/notes/upstream-revisions.txt"
printf 'Fable-2-Recomp: ' >> "$ROOT/notes/upstream-revisions.txt"
git -C "$ROOT/upstream/Fable-2-Recomp" rev-parse HEAD >> "$ROOT/notes/upstream-revisions.txt"
printf '\nFontes preparados: %s\n' "$ROOT"
printf '%s\n' 'IMPORTANTE: os arquivos .reference sao referencia e nao um port compilavel.'
printf '%s\n' 'O codigo Burnout precisa ser separado antes de montar um APK de Fable II.'
