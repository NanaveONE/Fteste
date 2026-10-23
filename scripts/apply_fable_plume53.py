#!/usr/bin/env python3
"""Patch only the verified Plume52 overlay with real Vulkan binding10 journal.

Append a host-coherent journal readout after the synchronous present fence.
Fail closed if the upstream overlay changed; do NOT pretend to commit physical
RAM while the guest-thread exclusion mechanism remains unimplemented.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

MARK = 'FABLE2_PLUME_53_JOURNAL'


def one(text: str, old: str, new: str, why: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f'{why}: expected 1 exact Plume52 anchor, found {count}')
    return text.replace(old, new, 1)


def patch_header(src: str) -> str:
    src=one(src,'  void FinishMemExport52();',
            '  void FinishMemExport52();\n'
            '  // FABLE2_PLUME_53_JOURNAL: read Vulkan writes only after fence.\n'
            '  void FinishMemExport53();', 'public journal callback')
    src=one(src,'  std::unique_ptr<plume::RenderBuffer> memexport52_stats_;',
            '  std::unique_ptr<plume::RenderBuffer> memexport52_stats_;\n'
            '  std::unique_ptr<plume::RenderBuffer> memexport53_journal_;\n'
            '  bool memexport53_enabled_ = false;', 'journal Vulkan resource')
    src=one(src,'  void* memexport52_stats_mapped_ = nullptr;',
            '  void* memexport52_stats_mapped_ = nullptr;\n'
            '  void* memexport53_journal_mapped_ = nullptr;', 'journal mapped pointer')
    return src


def patch_draw(src: str) -> str:
    src=one(src,'#include "fable_memexport52.h"',
            '#include "fable_memexport52.h"\n#include "fable_memexport_journal53.h"', 'journal include')
    src=one(src,'  draw_set_builder_.addReadWriteByteAddressBuffer(9);',
            '  draw_set_builder_.addReadWriteByteAddressBuffer(9);\n'
            '  // FABLE2_PLUME_53_JOURNAL: third real Vulkan storage binding.\n'
            '  draw_set_builder_.addReadWriteByteAddressBuffer(10);', 'descriptor set layout10')
    src=one(src,'  memexport52_stats_mapped_ = nullptr;',
            '  memexport52_stats_mapped_ = nullptr;\n'
            '  if (memexport53_journal_ && memexport53_journal_mapped_)\n'
            '    memexport53_journal_->unmap();\n'
            '  memexport53_journal_mapped_ = nullptr;', 'unmap readback journal')
    src=one(src,'  memexport52_stats_.reset();',
            '  memexport52_stats_.reset();\n'
            '  memexport53_journal_.reset();\n'
            '  memexport53_enabled_ = false;', 'free journal')
    anchor='  memexport52_enabled_ = want_memexport52;'
    addition='''  // FABLE2_PLUME_53_JOURNAL: Vulkan STORAGE descriptor 10.
  // The host-coherent READBACK allocation is directly shader-writable;
  // after Plume's synchronous submission fence, its contents are visible.
  // 52 already checks vertexPipelineStoresAndAtomics and disallows async.
  memexport53_enabled_ = want_memexport52 &&
      std::getenv("FABLE2_MEMEXPORT53_JOURNAL") != nullptr;
  const uint64_t journal_bytes = memexport53_enabled_ ?
      uint64_t(fable2::memexport53::kJournalBytes) : 16u;
  memexport53_journal_ = device_->createBuffer(plume::RenderBufferDesc::ReadbackBuffer(
      journal_bytes, plume::RenderBufferFlag::STORAGE));
  if (!memexport53_journal_ || !VulkanBufferOk(memexport53_journal_.get())) {
    REXLOG_ERROR("Fable MemExport53: Vulkan binding10 journal allocation failed");
    Shutdown();
    return false;
  }
  if (memexport53_enabled_) {
    memexport53_journal_mapped_ = memexport53_journal_->map();
    if (!memexport53_journal_mapped_) {
      REXLOG_ERROR("Fable MemExport53: HOST_COHERENT journal map failed");
      Shutdown();
      return false;
    }
    std::memset(memexport53_journal_mapped_, 0, fable2::memexport53::kJournalBytes);
  }
  REXLOG_INFO("Fable MemExport53: binding10 journal {} bytes; guest physical commit DISABLED",
              journal_bytes);
'''+anchor
    src=one(src,anchor,addition,'journal allocation')
    anchor='''    made.set->setBuffer(fable2::memexport52::kStatsDescriptorIndex,
                        memexport52_stats_.get(), fable2::memexport52::kStatsBytes);'''
    src=one(src,anchor,anchor+'''
    made.set->setBuffer(fable2::memexport53::kJournalDescriptorIndex,
                        memexport53_journal_.get(), memexport53_enabled_
                            ? fable2::memexport53::kJournalBytes : 16u);''',
            'journal descriptor setBuffer')
    fn='''// FABLE2_PLUME_53_JOURNAL: host-side validation AFTER completed fence.
// Plume53 does NOT have a proven exclusive guest-thread lock; it never calls
// Commit() or otherwise changes physical guest memory.
void PlumeDrawContext::FinishMemExport53() {
  if (!memexport53_enabled_) return;
  const auto stats = fable2::memexport52::ReadStatsAfterFence(
      memexport52_stats_mapped_, fable2::memexport52::kStatsBytes,
      true /* synchronous swapchain GPU submission fence completed */,
      true /* pinned Plume READBACK requires HOST_COHERENT */);
  if (!stats) {
    REXLOG_ERROR("Fable MemExport53: cannot read journal stats after Vulkan fence");
    return;
  }
  if (stats->reserved == 0 && stats->unsupported_format == 0 &&
      stats->invalid_address == 0 && stats->stored_vectors == 0) return;
  const auto journal = fable2::memexport53::Validate(
      memexport53_journal_mapped_, fable2::memexport53::kJournalBytes,
      *stats, true, true, fable2::memexport52::kGuestShadowBytes);
  if (!journal) {
    REXLOG_ERROR("Fable MemExport53: REJECT frame stores={} journal={} "
                 "unsupported={} invalid={} (guest RAM untouched)",
                 stats->stored_vectors, stats->reserved,
                 stats->unsupported_format, stats->invalid_address);
    return;
  }
  if (!journal->empty()) {
    REXLOG_INFO("Fable MemExport53: GPU produced {} verified journal entries, "
                "first physical byte address {:08X}, guest RAM commit DISABLED",
                journal->size(), journal->front().guest_address);
  }
}

'''
    src=one(src,'PlumeDrawContext::~PlumeDrawContext() {',
            fn+'PlumeDrawContext::~PlumeDrawContext() {','post-fence journal validation')
    return src


def patch_graphics(src: str) -> str:
    anchor='  if (draw_context_) draw_context_->FinishMemExport52();'
    return one(src,anchor,anchor+'\n  if (draw_context_) draw_context_->FinishMemExport53();',
               'GPU fence validated before journal read')


def prepare(xerenge_root:Path,base_overlay:Path,overlay:Path) -> dict:
    root,base,overlay=(p.resolve() for p in (xerenge_root,base_overlay,overlay))
    if overlay==base or overlay==root or root in overlay.parents:
        raise ValueError('Plume53 must be isolated from 52 and Xerenge checkout')
    parts={'plume_draw.cpp':(base/'plume_draw.cpp',patch_draw),
           'plume_graphics_system.cpp':(base/'plume_graphics_system.cpp',patch_graphics),
           'plume_renderer/plume_draw.h':(base/'plume_renderer/plume_draw.h',patch_header)}
    out={}
    for name,(src,fn) in parts.items():
        if not src.is_file(): raise ValueError('Missing Plume52 overlay: '+str(src))
        data=src.read_text()
        if MARK in data: raise ValueError('Refusing duplicate journal patch: '+name)
        out[name]=fn(data).encode()
    mf=overlay/'plume53-manifest.json'
    manifest={'patch':53,'stage':'Vulkan storage binding10 and post-fence journal VERIFY only',
              'guest_commit':False,
              'files':{name:hashlib.sha256(blob).hexdigest() for name,blob in out.items()}}
    if overlay.exists():
        if not mf.is_file() or json.loads(mf.read_text())!=manifest:
            raise ValueError('Existing overlay53 manifest differs')
        for name,data in out.items():
            if not (overlay/name).is_file() or (overlay/name).read_bytes()!=data:
                raise ValueError('Existing overlay53 file changed: '+name)
        print('PASS: identical Plume53 overlay already present')
        return manifest
    overlay.mkdir(parents=True)
    for name,blob in out.items():
        dst=overlay/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes(blob)
    mf.write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS: Plume53 uses real binding10 plus post-fence journal verification')
    print('PENDING: correctly gated guest RAM commit, shader format expansion, Android runtime')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xerenge-root',type=Path,required=True)
    p.add_argument('--base-overlay',type=Path,required=True)
    p.add_argument('--overlay',type=Path,required=True)
    a=p.parse_args()
    try:prepare(a.xerenge_root,a.base_overlay,a.overlay)
    except (ValueError,OSError,json.JSONDecodeError) as e:
        p.exit(2,f'BLOCKED: {e}\n')
if __name__=='__main__':main()
