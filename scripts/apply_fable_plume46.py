#!/usr/bin/env python3
"""Patch ONLY the generated, isolated Plume overlay, never upstream Xerenge.

Adds Vulkan set0 binding7 dynamically backed by Xenos loop constants from
SQ register 0x4908. Does NOT enable memory exports, storage buffer writes,
or claim playable Fable II; 583/588 remains the coverage gate.
"""
import argparse
from pathlib import Path
import hashlib
import json

MARK = 'FABLE2_PLUME_46_LOOP_BINDING'
HEADER_REL = Path('rexglue/src/plume_renderer/plume_draw.h')


def one(src: str, old: str, new: str, name: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f'{name}: upstream anchor needs exactly one occurrence, found {n}')
    return src.replace(old, new, 1)


def patch_header(s: str) -> str:
    s = one(s,
            '  SharedWords<192> fetch_constants;',
            '  SharedWords<192> fetch_constants;\n'
            '  // FABLE2_PLUME_46_LOOP_BINDING: raw Xenos 0x4908..0x4927 per-draw snapshot.\n'
            '  std::array<std::uint32_t, 32> fable_loop_words{};',
            'draw snapshot loop bank')
    s = one(s,
            '  std::unique_ptr<plume::RenderBuffer> shared_constants_;',
            '  std::unique_ptr<plume::RenderBuffer> shared_constants_;\n'
            '  std::unique_ptr<plume::RenderBuffer> fable_loop_constants_;',
            'draw loop buffer')
    s = one(s,
            '  void* shared_constants_mapped_ = nullptr;',
            '  void* shared_constants_mapped_ = nullptr;\n'
            '  void* fable_loop_constants_mapped_ = nullptr;',
            'draw loop mapped pointer')
    return s


def patch_graphics(s: str) -> str:
    # Executed after snapshot VS/PS/fetch constants are latched for the draw.
    # A full copy from live GPU registers avoids bogus zero-loop defaults.
    anchor = '  constants_as_last_[0] = constants_as_last_[1] = constants_as_last_[2] = true;'
    replacement = '''  // FABLE2_PLUME_46_LOOP_BINDING: capture real SQ loop constants for each draw.
  // LOAD_ALU_CONSTANT(type=3) maps these 32 words to GPU 0x4908..0x4927.
  for (std::uint32_t i = 0; i < 32; ++i) {
    snap.fable_loop_words[i] = gpu_registers_[0x4908u + i];
  }
''' + anchor
    return one(s, anchor, replacement, 'snapshot latching')


def patch_draw(s: str) -> str:
    s = one(s, '#include "plume_renderer/plume_draw.h"',
            '#include "plume_renderer/plume_draw.h"\n'
            '#include "fable_loop_constants_46.h"\n// FABLE2_PLUME_46_LOOP_BINDING',
            'GPU include')
    s = one(s, 'constexpr uint32_t kSharedConstantBytes = 512;',
            'constexpr uint32_t kSharedConstantBytes = 512;\n'
            'constexpr uint32_t kFableLoopConstantBytes = 512;',
            'loop buffer size')
    s = one(s, 'constexpr uint32_t kSharedSlotBytes = (kSharedConstantBytes + kCbAlign - 1) & ~(kCbAlign - 1);',
            'constexpr uint32_t kSharedSlotBytes = (kSharedConstantBytes + kCbAlign - 1) & ~(kCbAlign - 1);\n'
            'constexpr uint32_t kFableLoopSlotBytes = (kFableLoopConstantBytes + kCbAlign - 1) & ~(kCbAlign - 1);',
            'loop per-draw slot')
    s = one(s, '  if (shared_constants_ && shared_constants_mapped_) {\n    shared_constants_->unmap();\n  }',
            '  if (shared_constants_ && shared_constants_mapped_) {\n    shared_constants_->unmap();\n  }\n'
            '  if (fable_loop_constants_ && fable_loop_constants_mapped_) {\n'
            '    fable_loop_constants_->unmap();\n  }\n  fable_loop_constants_mapped_ = nullptr;',
            'unmap loop constants')
    s = one(s, '  shared_constants_.reset();',
            '  shared_constants_.reset();\n  fable_loop_constants_.reset();',
            'release loop buffer on shutdown')
    s = one(s, '  draw_set_builder_.addSampler(6, kDrawSlots);',
            '  draw_set_builder_.addSampler(6, kDrawSlots);\n'
            '  draw_set_builder_.addConstantBufferDynamic(7);',
            'descriptor set layout 7')
    s = one(s, '  shared_constants_ = make_cb(uint64_t(kSharedSlotBytes) * kCbSlots, "shared constants");',
            '  shared_constants_ = make_cb(uint64_t(kSharedSlotBytes) * kCbSlots, "shared constants");\n'
            '  fable_loop_constants_ = make_cb(uint64_t(kFableLoopSlotBytes) * kCbSlots, "Fable Xenos loop constants");',
            'loop buffer allocation')
    s = one(s, '  if (!vs_constants_ || !ps_constants_ || !shared_constants_) {',
            '  if (!vs_constants_ || !ps_constants_ || !shared_constants_ || !fable_loop_constants_) {',
            'loop buffer validation')
    s = one(s, '  shared_constants_mapped_ = shared_constants_->map();',
            '  shared_constants_mapped_ = shared_constants_->map();\n'
            '  fable_loop_constants_mapped_ = fable_loop_constants_->map();',
            'loop map')
    s = one(s, '  if (!vs_constants_mapped_ || !ps_constants_mapped_ || !shared_constants_mapped_) {',
            '  if (!vs_constants_mapped_ || !ps_constants_mapped_ || !shared_constants_mapped_ || !fable_loop_constants_mapped_) {',
            'loop map validation')
    s = one(s, '  std::memset(shared_constants_mapped_, 0, size_t(kSharedSlotBytes) * kCbSlots);',
            '  std::memset(shared_constants_mapped_, 0, size_t(kSharedSlotBytes) * kCbSlots);\n'
            '  std::memset(fable_loop_constants_mapped_, 0, size_t(kFableLoopSlotBytes) * kCbSlots);',
            'loop map initialization')
    s = one(s, '    made.set->setBuffer(2, shared_constants_.get(), kSharedConstantBytes);',
            '    made.set->setBuffer(2, shared_constants_.get(), kSharedConstantBytes);\n'
            '    // Descriptor builder order: 3 buffers, 4*16 texture/sampler, then binding7.\n'
            '    made.set->setBuffer(3 + 4 * kDrawSlots, fable_loop_constants_.get(), kFableLoopConstantBytes);',
            'bind dynamic buffer')
    s = one(s, '  uint32_t bound_offsets[3] = {~0u, ~0u, ~0u};',
            '  uint32_t bound_offsets[4] = {~0u, ~0u, ~0u, ~0u};',
            'four offsets cache')
    s = one(s, '    uint32_t shared_slot = slot_base + encoded;',
            '    uint32_t shared_slot = slot_base + encoded;\n'
            '    // Dedicated loop constants slot (never recycled for an in-flight draw).\n'
            '    const uint32_t fable_loop_slot = slot_base + encoded;',
            'loop slot allocation')
    s = one(s, '    EncodeStage("recording the draw");\n\n    const uint32_t constant_offsets[3] = {vs_slot * kVsSlotBytes, ps_slot * kPsSlotBytes,\n                                          shared_slot * kSharedSlotBytes};',
            '''    // SQ loop bank decoded into HLSL int4: x=count, y=start, z=signed-step.
    // Snapshot data is from the guest registers, NEVER manufactured zeros.
    const auto fable_loops = fable2::plume46::DecodeLoopConstants(snap.fable_loop_words.data());
    std::memcpy(static_cast<uint8_t*>(fable_loop_constants_mapped_) +
                fable_loop_slot * kFableLoopSlotBytes,
                fable_loops.data(), kFableLoopConstantBytes);
    EncodeStage("recording the draw");

    const uint32_t constant_offsets[4] = {vs_slot * kVsSlotBytes, ps_slot * kPsSlotBytes,
                                          shared_slot * kSharedSlotBytes,
                                          fable_loop_slot * kFableLoopSlotBytes};''',
            'write loop bank per draw')
    s = one(s, '      list->setGraphicsDescriptorSetDynamic(draw_set, 0, constant_offsets, 3);',
            '      list->setGraphicsDescriptorSetDynamic(draw_set, 0, constant_offsets, 4);',
            'bind four offsets')
    return s


def prepare(root: Path, base_overlay: Path, overlay: Path):
    root = root.resolve()
    base_overlay = base_overlay.resolve()
    overlay = overlay.resolve()
    if overlay == base_overlay:
        raise ValueError('Patch46 requires a separate overlay directory')
    if overlay == root or root in overlay.parents:
        raise ValueError('Patch46 output must not modify the Xerenge checkout')
    originals = {
        'plume_draw.cpp': (base_overlay / 'plume_draw.cpp', patch_draw),
        'plume_graphics_system.cpp': (base_overlay / 'plume_graphics_system.cpp', patch_graphics),
        'plume_renderer/plume_draw.h': (root / HEADER_REL, patch_header),
    }
    out = {}
    for name, (p, fn) in originals.items():
        if not p.is_file():
            raise ValueError('Missing overlay/upstream file: '+str(p))
        source = p.read_text(encoding='utf8')
        if MARK in source:
            raise ValueError('Refusing to apply 46 twice: '+name)
        out[name] = fn(source).encode('utf8')
    manifest = {
        'patch': 46,
        'status': 'Vulkan loop descriptor only; memexport storage still UNIMPLEMENTED',
        'files': {k: hashlib.sha256(v).hexdigest() for k,v in out.items()},
    }
    report = overlay / 'fable-memexport46-manifest.json'
    if overlay.exists():
        if not report.is_file() or json.loads(report.read_text()) != manifest:
            raise ValueError('Existing overlay46 is incompatible; review it manually')
        for name, blob in out.items():
            if not (overlay/name).is_file() or (overlay/name).read_bytes() != blob:
                raise ValueError('Existing overlay46 contains modified files: '+name)
        print('PASS: identical Plume46 overlay already exists')
        return
    overlay.mkdir(parents=True)
    for name, data in out.items():
        destination = overlay / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    report.write_text(json.dumps(manifest, indent=2)+'\n')
    print('PASS: Plume binding7 + real per-draw Xenos 32-word loop constants')
    print('BLOCKER: 5 memexport shaders still fail until Vulkan storage writes are implemented')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xerenge-root',type=Path,required=True)
    parser.add_argument('--base-overlay',type=Path,required=True)
    parser.add_argument('--overlay',type=Path,required=True)
    args=parser.parse_args()
    try: prepare(args.xerenge_root,args.base_overlay,args.overlay)
    except (ValueError,OSError) as exc:parser.exit(2,f'BLOCKED: {exc}\n')

if __name__=='__main__':main()
