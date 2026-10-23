#pragma once
// Vulkan MemExport readback handoff. The renderer owns the actual Vulkan
// compute/graphics submission, VkBuffer allocation, fence, and guest lock.
// This adapter validates completion and visibility BEFORE handing converted
// eM bytes to the tested MemExport 49 CPU writer. No fake Vulkan completion.
// Producer is REQUIRED to execute genuine MemExport shader stores; until it
// exists, this bridge is NOT called from live Plume draws.
#include "fable_memexport_sync_49.h"
#include <cstddef>
#include <cstdint>
#include <functional>
#include <span>
#include <vector>

namespace fable2::memexport50 {
struct GpuReadback {
  // These bytes MUST come from a completed GPU readback whose memory is made
  // host-visible by the actual Vulkan backend (not synthetic bytes).
  memexport47::Stream stream;
  unsigned export_index = 0;
  std::span<const std::byte> mapped;
  bool converted_from_xenos_format = false;
};

// Backend integration contract: wait_for_fence must call vkWaitForFences
// on the SUBMISSION fence; invalidate_mapped_memory must call
// vkInvalidateMappedMemoryRanges for noncoherent memory (and may return true
// for HOST_COHERENT allocations). The source buffer MUST transition from GPU
// storage writes to transfer/copy and readback in the command stream BEFORE
// the fence. This class cannot assert those barriers itself.
class ReadbackBridge {
 public:
  using Check = std::function<bool()>;
  using Dirty = std::function<void(std::size_t, std::size_t)>;
  bool Transfer(std::span<const GpuReadback> payloads,
                std::span<std::byte> guest_memory,
                bool guest_exclusive,
                const Check& wait_for_fence,
                const Check& invalidate_mapped_memory,
                const Dirty& dirty) {
    if (consumed_ || payloads.empty() || !guest_exclusive || !wait_for_fence ||
        !invalidate_mapped_memory || !dirty) return false;
    consumed_ = true;
    // In particular, do not even read the mapped buffers until the device
    // reports completion and the mapped range has been invalidated.
    if (!wait_for_fence() || !invalidate_mapped_memory()) return false;
    memexport49::ReadbackBatch batch;
    for (const auto& entry : payloads) {
      if (!entry.converted_from_xenos_format || entry.mapped.empty() ||
          !batch.Record(entry.stream, entry.export_index, entry.mapped)) return false;
    }
    if (!batch.Submit() || !batch.CompleteAfterFence(true, true)) return false;
    return batch.Commit(guest_memory, true, dirty);
  }
  bool consumed() const { return consumed_; }
 private:
  bool consumed_ = false;
};
}  // namespace fable2::memexport50
