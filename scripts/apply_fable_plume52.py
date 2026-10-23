#!/usr/bin/env python3
"""Add real Vulkan set0 SSBO bindings 8/9 to the verified Plume46 overlay.

Fail closed: exact, unique anchors; do not edit Xerenge; require a deterministic
hash-matched output; do not activate shader51 without a guest-memory journal.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

MARK = 'FABLE2_PLUME_52_STORAGE_BINDINGS'

def one(src: str, old: str, new: str, what: str) -> str:
    count = src.count(old)
    if count != 1:
        raise ValueError(f'{what}: expected exactly one source anchor; found {count}')
    return src.replace(old, new, 1)


def patch_header(s: str) -> str:
    s = one(s, '  bool Initialize(plume::RenderDevice* device);',
        '  bool Initialize(plume::RenderDevice* device);\n'
        '  // FABLE2_PLUME_52_STORAGE_BINDINGS: telemetry only, no guest commit.\n'
        '  void BeginMemExport52();\n'
        '  void FinishMemExport52();', '52 public interface')
    s = one(s, '  std::unique_ptr<plume::RenderBuffer> fable_loop_constants_;',
        '  std::unique_ptr<plume::RenderBuffer> fable_loop_constants_;\n'
        '  std::unique_ptr<plume::RenderBuffer> memexport52_memory_;\n'
        '  std::unique_ptr<plume::RenderBuffer> memexport52_stats_;\n'
        '  bool memexport52_enabled_ = false;', '52 storage members')
    s = one(s, '  void* fable_loop_constants_mapped_ = nullptr;',
        '  void* fable_loop_constants_mapped_ = nullptr;\n'
        '  void* memexport52_stats_mapped_ = nullptr;', '52 mapped stats')
    return s


def patch_draw(s: str) -> str:
    s = one(s, '#include "fable_loop_constants_46.h"',
        '#include "fable_loop_constants_46.h"\n#include "fable_memexport52.h"',
        '52 host stats include')
    s = one(s, '  fable_loop_constants_mapped_ = nullptr;',
        '  fable_loop_constants_mapped_ = nullptr;\n'
        '  if (memexport52_stats_ && memexport52_stats_mapped_)\n'
        '    memexport52_stats_->unmap();\n'
        '  memexport52_stats_mapped_ = nullptr;',
        '52 stats unmapping')
    s = one(s, '  fable_loop_constants_.reset();',
        '  fable_loop_constants_.reset();\n'
        '  memexport52_memory_.reset();\n'
        '  memexport52_stats_.reset();\n'
        '  memexport52_enabled_ = false;',
        '52 buffer cleanup')
    s = one(s, '  draw_set_builder_.addConstantBufferDynamic(7);',
        '  draw_set_builder_.addConstantBufferDynamic(7);\n'
        '  // FABLE2_PLUME_52_STORAGE_BINDINGS: 51 SPIR-V RWByteAddressBuffer.\n'
        '  draw_set_builder_.addReadWriteByteAddressBuffer(8);\n'
        '  draw_set_builder_.addReadWriteByteAddressBuffer(9);',
        '52 SSBO Vulkan layout')
    # Actual VkBuffer instances; READBACK memory is host-coherent in this
    # pinned Plume Vulkan allocator. Use a tiny binding while not explicitly
    # opted in, so existing non-MemExport games do not allocate 64 MiB.
    allocation = '''  // FABLE2_PLUME_52_STORAGE_BINDINGS: allocate *real* Vulkan storage buffers.
  // The 51 shader uses absolute guest byte addresses; until sparse mapping is
  // implemented, this opt-in experiment covers only the first 64 MiB.
  const bool want_memexport52 = std::getenv("FABLE2_MEMEXPORT52_PROBE") != nullptr;
  if (want_memexport52 && std::getenv("XERENGE_ASYNC_PRESENT") != nullptr) {
    REXLOG_ERROR("Fable MemExport52: async present is not supported; disable it");
    Shutdown();
    return false;
  }
  if (want_memexport52) {
    auto* vk = static_cast<plume::VulkanDevice*>(device_);
    VkPhysicalDeviceFeatures features{};
    if (!vkGetPhysicalDeviceFeatures || vk->physicalDevice == VK_NULL_HANDLE) {
      REXLOG_ERROR("Fable MemExport52: cannot query Vulkan vertex storage feature");
      Shutdown();
      return false;
    }
    vkGetPhysicalDeviceFeatures(vk->physicalDevice, &features);
    if (!features.vertexPipelineStoresAndAtomics) {
      REXLOG_ERROR("Fable MemExport52: vertexPipelineStoresAndAtomics unsupported");
      Shutdown();
      return false;
    }
  }
  const uint64_t shadow_bytes = want_memexport52
      ? uint64_t(fable2::memexport52::kGuestShadowBytes) : 16u;
  // The READBACK allocator requires HOST_COHERENT, so CPU reads after the
  // swapchain submission fence need no vkInvalidateMappedMemoryRanges.
  memexport52_memory_ = device_->createBuffer(plume::RenderBufferDesc::ReadbackBuffer(
      shadow_bytes, plume::RenderBufferFlag::STORAGE));
  memexport52_stats_ = device_->createBuffer(plume::RenderBufferDesc::ReadbackBuffer(
      fable2::memexport52::kStatsBytes, plume::RenderBufferFlag::STORAGE));
  if (!memexport52_memory_ || !memexport52_stats_ ||
      !VulkanBufferOk(memexport52_memory_.get()) ||
      !VulkanBufferOk(memexport52_stats_.get())) {
    REXLOG_ERROR("Fable MemExport52: Vulkan storage buffer allocation failed");
    Shutdown();
    return false;
  }
  memexport52_stats_mapped_ = memexport52_stats_->map();
  if (!memexport52_stats_mapped_) {
    REXLOG_ERROR("Fable MemExport52: HOST_COHERENT stats mapping unavailable");
    Shutdown();
    return false;
  }
  std::memset(memexport52_stats_mapped_, 0, fable2::memexport52::kStatsBytes);
  memexport52_enabled_ = want_memexport52;
  REXLOG_INFO("Fable MemExport52: bound storage 8 ({} bytes) and 9 ({} bytes), "
              "guest commit DISABLED", shadow_bytes, fable2::memexport52::kStatsBytes);
'''
    s = one(s, '  fable_loop_constants_ = make_cb(uint64_t(kFableLoopSlotBytes) * kCbSlots, "Fable Xenos loop constants");',
        '  fable_loop_constants_ = make_cb(uint64_t(kFableLoopSlotBytes) * kCbSlots, "Fable Xenos loop constants");\n'+ allocation,
        '52 create readback storage buffers')
    # Descriptor index is *flattened*, not the Vulkan binding number:
    # 3 constant descriptors + 64 textures/samplers + 1 loop CB = 68.
    s = one(s,
        '    made.set->setBuffer(3 + 4 * kDrawSlots, fable_loop_constants_.get(), kFableLoopConstantBytes);',
        '''    made.set->setBuffer(3 + 4 * kDrawSlots, fable_loop_constants_.get(), kFableLoopConstantBytes);
    made.set->setBuffer(fable2::memexport52::kMemoryDescriptorIndex,
                        memexport52_memory_.get(), memexport52_enabled_
                            ? fable2::memexport52::kGuestShadowBytes : 16u);
    made.set->setBuffer(fable2::memexport52::kStatsDescriptorIndex,
                        memexport52_stats_.get(), fable2::memexport52::kStatsBytes);''',
        '52 real Vulkan descriptor writes')
    # Add telemetry readout, but NEVER copy data into guest memory: SPIR-V 51
    # does not report the written addresses, so that would silently corrupt RAM.
    funcs = '''// FABLE2_PLUME_52_STORAGE_BINDINGS: actual host-coherent GPU storage telemetry.
// Begin must execute only after the prior default synchronous present fence.
void PlumeDrawContext::BeginMemExport52() {
  if (!memexport52_enabled_ || !memexport52_stats_mapped_) return;
  std::memset(memexport52_stats_mapped_, 0, fable2::memexport52::kStatsBytes);
}

// The stock synchronous PlumeSwapchain::ClearAndPresent waits on its GPU
// submission fence before returning; XERENGE_ASYNC_PRESENT is forbidden above.
void PlumeDrawContext::FinishMemExport52() {
  if (!memexport52_enabled_) return;
  const auto values = fable2::memexport52::ReadStatsAfterFence(
      memexport52_stats_mapped_, fable2::memexport52::kStatsBytes,
      true /* default swapchain fence waited */, true /* host coherent */);
  if (!values) {
    REXLOG_ERROR("Fable MemExport52: GPU storage stats not host-visible");
    return;
  }
  if (values->unsupported_format || values->invalid_address || values->stored_vectors) {
    REXLOG_WARN("Fable MemExport52: GPU stores={} unsupported={} rejected={} "
                "(not synchronized with guest RAM)",
                values->stored_vectors, values->unsupported_format, values->invalid_address);
  }
}

'''
    s = one(s, 'PlumeDrawContext::~PlumeDrawContext() {',funcs + 'PlumeDrawContext::~PlumeDrawContext() {',
            '52 telemetry member functions')
    return s


def patch_graphics(s: str) -> str:
    s = one(s,
        '  swapchain_->ClearAndPresent(0.03f, 0.04f, 0.07f, 1.0f, encode, &ctx, resolve, hold);',
        '''  // FABLE2_PLUME_52_STORAGE_BINDINGS: reset CPU-coherent stats before GPU
  // submission; the synchronous present waits for the submission fence.
  if (draw_context_) draw_context_->BeginMemExport52();
  swapchain_->ClearAndPresent(0.03f, 0.04f, 0.07f, 1.0f, encode, &ctx, resolve, hold);
  if (draw_context_) draw_context_->FinishMemExport52();''',
        '52 fenced guest-frame entry')
    return s


def prepare(xerenge_root: Path, base_overlay: Path, overlay: Path):
    xerenge_root, base_overlay, overlay = (p.resolve() for p in
                                           (xerenge_root, base_overlay, overlay))
    if overlay == base_overlay or overlay == xerenge_root or xerenge_root in overlay.parents:
        raise ValueError('Plume52 output must be separate from upstream and overlay46')
    parts = {
      'plume_draw.cpp': (base_overlay/'plume_draw.cpp',patch_draw),
      'plume_graphics_system.cpp': (base_overlay/'plume_graphics_system.cpp',patch_graphics),
      'plume_renderer/plume_draw.h': (base_overlay/'plume_renderer/plume_draw.h',patch_header),
    }
    out={}
    for name,(file,fn) in parts.items():
        if not file.is_file():raise ValueError('Missing Plume46 overlay: '+str(file))
        source=file.read_text()
        if MARK in source: raise ValueError('Cannot apply Plume52 twice')
        out[name]=fn(source).encode()
    manifest={'patch':52,'stage':'real GPU SSBO bindings and coherent stats; NO guest-memory writes',
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in out.items()}}
    mf=overlay/'plume52-manifest.json'
    if overlay.exists():
        if not mf.is_file() or json.loads(mf.read_text())!=manifest:
            raise ValueError('Existing Plume52 output has different manifest')
        for name,data in out.items():
            if not (overlay/name).is_file() or (overlay/name).read_bytes()!=data:
                raise ValueError('Existing Plume52 output was modified: '+name)
        print('PASS: existing identical Plume52 overlay')
        return
    overlay.mkdir(parents=True)
    for name,data in out.items():
        path=overlay/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    mf.write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS: Plume52 Vulkan RWByteAddressBuffer bindings 8/9 with synchronized stats')
    print('REMAINING: Xenos MemExport write-address journal and guest RAM commit')


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--xerenge-root',type=Path,required=True)
    a.add_argument('--base-overlay',type=Path,required=True)
    a.add_argument('--overlay',type=Path,required=True)
    args=a.parse_args()
    try:prepare(args.xerenge_root,args.base_overlay,args.overlay)
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        a.exit(2,f'BLOCKED: {exc}\n')

if __name__=='__main__':main()
