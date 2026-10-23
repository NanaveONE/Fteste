#pragma once
// Fable II MemExport 49: checked handoff from a completed GPU readback to
// the existing CPU-side guest-memory writer (47). No Vulkan calls are faked.
// Vulkan producer MUST signal completion and hand back correctly formatted
// bytes; caller MUST ensure CPU guest memory is quiesced during Commit().
#include "fable_memexport_writer_47.h"
#include <cstddef>
#include <cstdint>
#include <functional>
#include <span>
#include <vector>

namespace fable2::memexport49 {

// Staging state is linear: submitted -> GPU complete -> host commit.
// A caller MUST NOT reuse a batch after completion or failure.
enum class State { Recording, Submitted, GpuComplete, Committed, Failed };
struct Entry {
  memexport47::Stream stream;
  unsigned export_index;
  std::vector<std::byte> value;
};

class ReadbackBatch {
 public:
  bool Record(const memexport47::Stream& stream, unsigned export_index,
              std::span<const std::byte> converted_gpu_bytes) {
    if (state_ != State::Recording || converted_gpu_bytes.empty()) return false;
    // Verify export arguments and payload before recording. Since the real
    // guest-memory span may not be known yet, use max-sized permitted RAM.
    if (!memexport47::Plan(stream, export_index, 512ull << 20,
                           converted_gpu_bytes.size())) return false;
    entries_.push_back(Entry{stream, export_index,
                             {converted_gpu_bytes.begin(), converted_gpu_bytes.end()}});
    return true;
  }
  bool Submit() {
    if (state_ != State::Recording || entries_.empty()) return false;
    state_ = State::Submitted;
    return true;
  }
  // The GPU integration must call this only AFTER Vulkan fence wait and
  // host-visible invalidate (for non-coherent allocations). The callback
  // reports both operations' results. False fails CLOSED.
  bool CompleteAfterFence(bool fence_wait_ok, bool mapped_memory_invalidate_ok) {
    if (state_ != State::Submitted) return false;
    if (!fence_wait_ok || !mapped_memory_invalidate_ok) {
      state_ = State::Failed;
      return false;
    }
    state_ = State::GpuComplete;
    return true;
  }
  // Atomic validation: inspect *all* destinations before copying any bytes.
  // Caller owns the CPU/guest memory exclusion and cache invalidation.
  bool Commit(std::span<std::byte> guest_memory, bool guest_memory_exclusive,
              const std::function<void(std::size_t, std::size_t)>& on_dirty) {
    if (state_ != State::GpuComplete || !guest_memory_exclusive || !on_dirty) return false;
    for (const auto& e : entries_) {
      if (!memexport47::Plan(e.stream, e.export_index, guest_memory.size(), e.value.size())) {
        state_ = State::Failed;
        return false;
      }
    }
    memexport47::MemoryWriter writer{guest_memory};
    for (const auto& e : entries_) {
      if (!writer.Store(e.stream, e.export_index, e.value)) {
        state_ = State::Failed;
        return false;
      }
    }
    // Notify dirty ranges only after complete successful copy.
    for (const auto& range : writer.dirty()) on_dirty(range.begin, range.end);
    state_ = State::Committed;
    return true;
  }
  State state() const { return state_; }
  std::size_t size() const { return entries_.size(); }
 private:
  State state_ = State::Recording;
  std::vector<Entry> entries_;
};
} // namespace fable2::memexport49
