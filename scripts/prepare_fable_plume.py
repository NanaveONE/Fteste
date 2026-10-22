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
GRAPHICS_SOURCE = Path('rexglue/src/plume_renderer/plume_graphics_system.cpp')
OUTPUT_NAME = 'plume_draw.cpp'
GRAPHICS_OUTPUT_NAME = 'plume_graphics_system.cpp'
PATCH_VERSION = 2

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


# Xerenge only dumps shaders on demand, to its working directory. On
# Android the cwd is not a reliable, writable place, and the capture must be
# tied to the Fable II installation rather than Burnout's generated/ tree.
# This is a REAL C++ source patch: it changes where the existing PM4
# microcode capture/wrapper logic writes its input for XenosRecomp.
DUMP_ENABLE = '  static const bool dumping = std::getenv("XERENGE_DUMP_UCODE") != nullptr;'
DUMP_ENABLE_FABLE = '''#if defined(FABLE2_PLUME_PORT)
  static const bool dumping = std::getenv("FABLE2_DUMP_UCODE") != nullptr;
#else
  static const bool dumping = std::getenv("XERENGE_DUMP_UCODE") != nullptr;
#endif'''
DUMP_MKDIR = '  std::filesystem::create_directories("generated/ucode-dump", ec);'
DUMP_DIR = '  const auto dir = std::filesystem::path("generated/ucode-dump");'
DUMP_MKDIR_FABLE = '''#if defined(FABLE2_PLUME_PORT)
  // Game-specific Android storage: no shader dumps into the read-only APK
  // native libraries or the bundled source tree. Capture only when opted in.
  const char* writable_root = std::getenv("FABLE2_USER_ROOT");
  if (!writable_root || !*writable_root) {
    REXLOG_ERROR("FABLE2_DUMP_UCODE needs FABLE2_USER_ROOT");
    return;
  }
  const auto dir = std::filesystem::path(writable_root) / "shader-captures" / "ucode-dump";
  std::filesystem::create_directories(dir, ec);
  if (ec) {
    REXLOG_ERROR("Fable II shader capture directory not writable: {}", ec.message());
    return;
  }
#else
  std::filesystem::create_directories("generated/ucode-dump", ec);
  const auto dir = std::filesystem::path("generated/ucode-dump");
#endif'''


def patch_graphics_system(source: str) -> str:
    for label, anchor in [('shader capture switch', DUMP_ENABLE),
                          ('shader capture folder', DUMP_MKDIR),
                          ('shader capture path', DUMP_DIR)]:
        if source.count(anchor) != 1:
            raise ValueError(f'{label}: expected one Xerenge anchor, found {source.count(anchor)}')
    result = source.replace(DUMP_ENABLE, DUMP_ENABLE_FABLE)
    # One controlled replacement removes both old directory anchors and puts
    # the new dir in scope for the rest of DumpMicrocode, with no redeclaration.
    start = result.index(DUMP_MKDIR)
    end = result.index(DUMP_DIR, start) + len(DUMP_DIR)
    between = result[start + len(DUMP_MKDIR):result.index(DUMP_DIR, start)]
    # Preserve the snprintf block with the filename; it uses no dir.
    if 'std::snprintf(name,' not in between:
        raise ValueError('Xerenge shader capture layout changed')
    result = result[:start] + DUMP_MKDIR_FABLE + '\n' + between.replace(DUMP_DIR, '') + result[end:]
    if result.count('FABLE2_DUMP_UCODE') < 2:
        raise ValueError('Fable capture overlay not applied')
    return result


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
    output = output.expanduser().resolve()
    sources = {RELATIVE_SOURCE: (OUTPUT_NAME, patch),
               GRAPHICS_SOURCE: (GRAPHICS_OUTPUT_NAME, patch_graphics_system)}
    if output == xerenge_root or xerenge_root in output.parents:
        raise ValueError('Overlay must be separate from Xerenge upstream source')
    created = {}
    checksums = {}
    for relative, (filename, transformer) in sources.items():
        source = xerenge_root / relative
        if not source.is_file():
            raise ValueError(f'Xerenge Plume source not found: {source}')
        original = source.read_bytes()
        try:
            changed = transformer(original.decode('utf-8')).encode('utf-8')
        except UnicodeDecodeError as err:
            raise ValueError('Upstream Plume source is not UTF-8') from err
        created[filename] = changed
        checksums[filename] = {'source': str(relative),
                               'upstream_sha256': sha256(original),
                               'patched_sha256': sha256(changed)}
    manifest = {
        'title': 'Fable II Plume graphics overlay',
        'patch_version': PATCH_VERSION,
        'files': checksums,
        'source_relative_path': RELATIVE_SOURCE.as_posix(),
        'upstream_sha256': checksums[OUTPUT_NAME]['upstream_sha256'],
        'patched_sha256': checksums[OUTPUT_NAME]['patched_sha256'],
        'changes': ['Fable-specific guest culling', 'bounded missing-pipeline diagnostics',
                    'opt-in writable runtime shader capture in Fable II storage'],
        'status': 'source overlay only; not proven to render Fable II',
    }
    report = output / 'plume-overlay.json'
    if output.exists():
        if not report.is_file():
            raise ValueError('Overlay directory exists but is incomplete. Review before deleting.')
        try:
            existing = json.loads(report.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError('Invalid existing overlay manifest') from err
        if existing != manifest or any(not (output / key).is_file() or
                                       sha256((output / key).read_bytes()) != sha256(blob)
                                       for key, blob in created.items()):
            raise ValueError('Overlay out of date / modified. Review and remove old overlay before retrying.')
        return manifest
    output.mkdir(parents=True)
    for filename, data in created.items():
        (output / filename).write_bytes(data)
    report.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
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
