#!/usr/bin/env python3
"""Create isolated overlay 55 on top of 53, without writing the Xerenge tree.

This adds a real, guarded guest physical-memory commit adapter. No stop-world
host is implemented by stock Plume or configured here; it remains fail closed.
"""
import argparse
import hashlib
import json
from pathlib import Path

MARK = 'FABLE2_PLUME_55_GUEST_TRANSACTION'


def one(src: str, old: str, new: str, label: str) -> str:
    count = src.count(old)
    if count != 1:
        raise ValueError(f'{label}: expected exactly one anchor, found {count}')
    return src.replace(old, new, 1)


def patch_header(src: str) -> str:
    src = one(src, '#pragma once', '#pragma once\n#include "fable_memexport_guest55.h"\n'
              '// FABLE2_PLUME_55_GUEST_TRANSACTION: validated physical host interface.', 'header import')
    src = one(src, '  void FinishMemExport53();',
              '  void FinishMemExport53();\n'
              '  void FinishMemExport55();\n'
              '  // Only trusted SDK code that stops every guest thread may install this host.\n'
              '  void SetPhysicalMemoryHost55(fable2::memexport55::PhysicalMemoryHost* host);',
              'public guarded commit interface')
    src = one(src, '  bool memexport53_enabled_ = false;',
              '  bool memexport53_enabled_ = false;\n'
              '  fable2::memexport55::PhysicalMemoryHost* memexport55_host_ = nullptr;',
              'opt-in host pointer')
    return src


def patch_draw(src: str) -> str:
    # The header includes the host contract, so no duplicate include here.
    src = one(src, 'guest RAM commit DISABLED',
              'guest RAM commit requires certified Plume55 exclusive host',
              'remove obsolete unconditional 53 status')
    anchor = 'PlumeDrawContext::~PlumeDrawContext() {'
    fn = '''// FABLE2_PLUME_55_GUEST_TRANSACTION: Never infer guest exclusion from a
// Vulkan fence; the fence covers GPU commands, not concurrent guest CPU threads.
void PlumeDrawContext::SetPhysicalMemoryHost55(
    fable2::memexport55::PhysicalMemoryHost* host) {
  memexport55_host_ = host;  // Caller owns lifetime; must outlive this draw context.
}

void PlumeDrawContext::FinishMemExport55() {
  if (!memexport53_enabled_ || !memexport55_host_ ||
      !memexport53_journal_mapped_ || !memexport52_stats_mapped_) return;
  // Called after the same synchronous fence as FinishMemExport53. Async
  // present is forbidden by 52 when the experiment is enabled.
  const auto stats = fable2::memexport52::ReadStatsAfterFence(
      memexport52_stats_mapped_, fable2::memexport52::kStatsBytes,
      true /* Plume synchronous GPU fence completed */,
      true /* Plume readback allocation requires HOST_COHERENT */);
  if (!stats || (stats->reserved == 0 && stats->stored_vectors == 0)) return;
  const auto result = fable2::memexport55::CommitFencedJournal(
      memexport53_journal_mapped_, fable2::memexport53::kJournalBytes,
      *stats, true, true, memexport55_host_,
      fable2::memexport52::kGuestShadowBytes);
  if (!result) {
    REXLOG_ERROR("Fable MemExport55: guest write rejected status={} entries={} "
                 "(physical RAM untouched)", int(result.status), result.entries);
  } else {
    REXLOG_INFO("Fable MemExport55: committed {} fenced physical write(s) "
                "under verified guest-thread exclusion", result.entries);
  }
}

'''
    return one(src, anchor, fn + anchor, 'fenced journal runtime hook')


def patch_graphics(src: str) -> str:
    anchor = '  if (draw_context_) draw_context_->FinishMemExport53();'
    return one(src, anchor, anchor + '\n'
               '  // FABLE2_PLUME_55_GUEST_TRANSACTION: requires an externally\n'
               '  // installed, certified guest stop-the-world memory host.\n'
               '  if (draw_context_) draw_context_->FinishMemExport55();',
               'post-fence hook')


def prepare(xerenge_root: Path, base_overlay: Path, overlay: Path) -> dict:
    root, base, overlay = (p.resolve() for p in (xerenge_root, base_overlay, overlay))
    if overlay == base or overlay == root or root in overlay.parents:
        raise ValueError('Overlay55 must not overwrite overlay53 or the Xerenge checkout')
    sources = {
        'plume_draw.cpp': (base/'plume_draw.cpp', patch_draw),
        'plume_graphics_system.cpp': (base/'plume_graphics_system.cpp', patch_graphics),
        'plume_renderer/plume_draw.h': (base/'plume_renderer/plume_draw.h', patch_header),
    }
    output = {}
    for name, (path, fn) in sources.items():
        if not path.is_file():
            raise ValueError('Missing verified overlay53: '+str(path))
        original = path.read_text()
        if MARK in original:
            raise ValueError('Refusing duplicate 55 overlay in '+name)
        output[name] = fn(original).encode()
    manifest = {'patch':55,
                'stage':'post-fence physical guest transaction hook, host adapter required',
                'stock_plume_guest_commit_enabled':False,
                'files':{k:hashlib.sha256(v).hexdigest() for k,v in output.items()}}
    report = overlay/'plume55-manifest.json'
    if overlay.exists():
        if not report.is_file() or json.loads(report.read_text()) != manifest:
            raise ValueError('Existing overlay55 manifest differs')
        for name, blob in output.items():
            if not (overlay/name).is_file() or (overlay/name).read_bytes() != blob:
                raise ValueError('Existing overlay55 file modified: '+name)
        print('PASS: identical Plume55 overlay already installed')
        return manifest
    overlay.mkdir(parents=True)
    for name, blob in output.items():
        out = overlay/name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
    report.write_text(json.dumps(manifest, indent=2)+'\n')
    print('PASS: 55 fenced Vulkan journal -> exclusive-memory commit bridge')
    print('BLOCKED: no certified ReXGlue guest stop-the-world adapter in current SDK')
    return manifest


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--xerenge-root', type=Path, required=True)
    a.add_argument('--base-overlay', type=Path, required=True)
    a.add_argument('--overlay', type=Path, required=True)
    ns=a.parse_args()
    try: prepare(ns.xerenge_root,ns.base_overlay,ns.overlay)
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        a.exit(2,'BLOCKED: '+str(exc)+'\n')
if __name__=='__main__': main()
