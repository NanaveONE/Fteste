#!/usr/bin/env python3
"""Patch an isolated copy of Plume's draw pipeline for Fable II.

Never modify the Xerenge submodule. Fail on changed upstream anchors and
require a reproducible hash-matched overlay before building a native plugin.
The patch fixes only two *identified* defaults; it is NOT a gameplay renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RELATIVE_SOURCE = Path('rexglue/src/plume_renderer/plume_draw.cpp')
OUTPUT_NAME = 'plume_draw.cpp'
PATCH_VERSION = 1

CULL_ANCHOR = '''  static const bool culling = std::getenv("XERENGE_CULL") != nullptr;
  cull = culling ? (cull & 7u) : 0u;'''
CULL_PATCH = '''  // Fable II: honor the Xenos guest's PA_SU_SC_MODE_CNTL state by default.
  // The Xerenge/Burnout default disables culling; that can remove depth-
  // correct silhouettes in Fable II. For debugging, set
  // FABLE2_DISABLE_GUEST_CULL=1 to return to Xerenge's no-culling mode.
#if defined(FABLE2_PLUME_PORT)
  static const bool culling = std::getenv("FABLE2_DISABLE_GUEST_CULL") == nullptr;
#else
  static const bool culling = std::getenv("XERENGE_CULL") != nullptr;
#endif
  cull = culling ? (cull & 7u) : 0u;'''

MISS_ANCHOR = '''  if (!vs || !ps) {
    static uint32_t miss_logs = 0;
    if (miss_logs < 8) {
      ++miss_logs;
      REXLOG_WARN("plume: draw pipeline skipped vs={:016X} ({}) ps={:016X} ({})", vs_hash,
                  vs ? "ok" : "miss", ps_hash, ps ? "ok" : "miss");
    }
    return nullptr;
  }'''
MISS_PATCH = '''  if (!vs || !ps) {
    // A Fable II shader coverage run can expose hundreds of distinct missing
    // shaders, not just the first 8 draws. Report each missing hash pair once,
    // with bounded memory and log output. Never replace the shader with a
    // visually convincing but incorrect fallback.
#if defined(FABLE2_PLUME_PORT)
    static std::mutex fable2_miss_mutex;
    static std::set<std::pair<uint64_t, uint64_t>> fable2_missing_pairs;
    std::lock_guard lock(fable2_miss_mutex);
    if (fable2_missing_pairs.size() < 1024 &&
        fable2_missing_pairs.emplace(vs_hash, ps_hash).second) {
      REXLOG_WARN("plume: FABLE2_MISSING_PIPELINE vs={:016X} ({}) ps={:016X} ({})", vs_hash,
                  vs ? "ok" : "miss", ps_hash, ps ? "ok" : "miss");
    }
#else
    static uint32_t miss_logs = 0;
    if (miss_logs < 8) {
      ++miss_logs;
      REXLOG_WARN("plume: draw pipeline skipped vs={:016X} ({}) ps={:016X} ({})", vs_hash,
                  vs ? "ok" : "miss", ps_hash, ps ? "ok" : "miss");
    }
#endif
    return nullptr;
  }'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch(source: str) -> str:
    for anchor in (CULL_ANCHOR, MISS_ANCHOR):
        if source.count(anchor) != 1:
            raise ValueError(f'Plume upstream changed; anchor appears {source.count(anchor)} times: {anchor[:95]}')
    result = source.replace(CULL_ANCHOR, CULL_PATCH).replace(MISS_ANCHOR, MISS_PATCH)
    if result == source or result.count('FABLE2_MISSING_PIPELINE') != 1:
        raise ValueError('Patch was not applied exactly once')
    return result


def prepare(xerenge_root: Path, output: Path) -> dict:
    xerenge_root = xerenge_root.expanduser().resolve()
    source = xerenge_root / RELATIVE_SOURCE
    output = output.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f'Xerenge Plume source not found: {source}')
    if output == xerenge_root or xerenge_root in output.parents or source.is_relative_to(output):
        raise ValueError('Overlay must be separate from Xerenge upstream source')
    original = source.read_bytes()
    try:
        text = original.decode('utf-8')
    except UnicodeDecodeError as err:
        raise ValueError('Upstream Plume source is not UTF-8') from err
    changed = patch(text).encode('utf-8')
    manifest = {
        'title': 'Fable II Plume draw overlay',
        'patch_version': PATCH_VERSION,
        'source_relative_path': RELATIVE_SOURCE.as_posix(),
        'upstream_sha256': sha256(original),
        'patched_sha256': sha256(changed),
        'changes': ['Fable-specific guest culling', 'one warning per missing shader pair (max 1024)'],
        'status': 'source overlay only; not proven to render Fable II',
    }
    patched_path = output / OUTPUT_NAME
    report_path = output / 'plume-overlay.json'
    if output.exists():
        if not patched_path.is_file() or not report_path.is_file():
            raise ValueError('Overlay directory exists but is incomplete. Review before deleting.')
        try:
            existing = json.loads(report_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError('Invalid existing overlay manifest') from err
        if existing != manifest or sha256(patched_path.read_bytes()) != sha256(changed):
            raise ValueError('Overlay out of date / modified. Review and remove old overlay before retrying.')
        return manifest
    output.mkdir(parents=True)
    patched_path.write_bytes(changed)
    report_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xerenge-root', type=Path, default=Path('external/Xerenge'))
    parser.add_argument('--output', type=Path, default=Path('build/fable2-plume-overlay'))
    args = parser.parse_args()
    try:
        result = prepare(args.xerenge_root, args.output)
    except (ValueError, OSError) as err:
        parser.exit(2, f'BLOCKED: {err}\n')
    print('OK: Plume Fable II overlay validated: ' + result['patched_sha256'])
    print('NOTE: GPU behavior remains untested without a real Fable II run.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
