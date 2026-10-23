#pragma once
// Fable II GPU MemExport 47: checked CPU-side linear guest-memory writer.
// This is an actual memory-copy implementation for already-decoded eM bytes,
// but it is NOT a Vulkan storage-buffer implementation. Do not call it from a
// live graphics draw without proper GPU/CPU synchronization.
#include <array>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <span>
#include <vector>

namespace fable2::memexport47 {
struct Stream {
  std::uint32_t base_address;
  std::uint32_t first_index;
  std::uint32_t element_count;
  std::uint8_t element_bytes;
  std::uint8_t endian;
  std::uint8_t number_format;
  bool red_blue_swap;
};
struct DirtyRange { std::size_t begin; std::size_t end; };
struct WriteResult { std::size_t start; std::size_t bytes; };
// Exact-copy mode only, to avoid fabricating Xenos format conversion.
// Element count is total count, not the number of writes remaining.
inline std::optional<WriteResult> Plan(const Stream& s, unsigned export_index,
                                       std::size_t memory_size,
                                       std::size_t payload_size) {
  if (export_index > 4 || s.first_index >= s.element_count ||
      (s.element_bytes != 1 && s.element_bytes != 2 &&
       s.element_bytes != 4 && s.element_bytes != 8 &&
       s.element_bytes != 16) ||
      s.endian != 0 || s.number_format != 0 || s.red_blue_swap ||
      payload_size != s.element_bytes) return std::nullopt;
  const std::uint64_t element = std::uint64_t(s.first_index) + export_index;
  if (element >= s.element_count) return std::nullopt;
  const std::uint64_t off = std::uint64_t(s.base_address) + element * s.element_bytes;
  if (off > memory_size || s.element_bytes > memory_size - off) return std::nullopt;
  return WriteResult{static_cast<std::size_t>(off), s.element_bytes};
}
class MemoryWriter {
 public:
  explicit MemoryWriter(std::span<std::byte> guest_memory) : memory_(guest_memory) {}
  // Must be called only after GPU ownership has been acquired by the caller.
  // Source can alias guest memory; memmove handles overlap correctly.
  bool Store(const Stream& stream, unsigned export_index,
             std::span<const std::byte> payload) {
    const auto plan = Plan(stream, export_index, memory_.size(), payload.size());
    if (!plan) return false;
    std::memmove(memory_.data() + plan->start, payload.data(), plan->bytes);
    MergeDirty({plan->start, plan->start + plan->bytes});
    return true;
  }
  std::span<const DirtyRange> dirty() const { return dirty_; }
  void ClearDirtyAfterHostSync() { dirty_.clear(); }
 private:
  void MergeDirty(DirtyRange range) {
    auto it = dirty_.begin();
    while (it != dirty_.end()) {
      if (it->end < range.begin || it->begin > range.end) { ++it; continue; }
      range.begin = std::min(range.begin, it->begin);
      range.end = std::max(range.end, it->end);
      it = dirty_.erase(it);
    }
    auto pos = std::lower_bound(dirty_.begin(), dirty_.end(), range.begin,
       [](const DirtyRange& a, std::size_t value){return a.begin < value;});
    dirty_.insert(pos, range);
  }
  std::span<std::byte> memory_;
  std::vector<DirtyRange> dirty_;
};
}  // namespace fable2::memexport47
