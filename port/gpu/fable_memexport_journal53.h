#pragma once
// Public, platform-neutral verification of *fenced* Vulkan MemExport journals.
// Plume53 fills the journal via a real Vulkan storage buffer (binding 10).
// A successful parse NEVER implies guest memory may be written without an
// external stop-the-world / guest-thread exclusion protocol.
#include "fable_memexport52.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <optional>
#include <span>
#include <vector>

namespace fable2::memexport53 {
constexpr std::uint32_t kTag = 0xF2B1E053u;
constexpr std::size_t kVectorBytes = 16;
constexpr std::size_t kEntryBytes = 32;
constexpr std::size_t kCapacity = 32768;
constexpr std::size_t kJournalBytes = kEntryBytes * kCapacity;
constexpr unsigned kJournalBinding = 10;
constexpr unsigned kJournalDescriptorIndex = memexport52::kStatsDescriptorIndex + 1;

struct Entry {
  std::uint32_t guest_address = 0;
  std::uint32_t byte_count = 0;
  std::uint32_t data[4]{};
  std::uint32_t tag = 0;
  std::uint32_t address_complement = 0;
};
static_assert(sizeof(Entry) == kEntryBytes);

// 52: Stats.reserved is the journal's atomically reserved entry count.
// Invalid/unsupported writes, overflow, inconsistent publication and
// overlapping addresses invalidate the ENTIRE batch (no partial commit).
inline std::optional<std::vector<Entry>> Validate(
    const void* mapped, std::size_t size, const memexport52::Stats& stats,
    bool fence_completed, bool host_visible, std::size_t guest_shadow_size) {
  if (!mapped || !fence_completed || !host_visible ||
      stats.unsupported_format != 0 || stats.invalid_address != 0 ||
      stats.reserved > kCapacity || stats.stored_vectors != stats.reserved ||
      guest_shadow_size < kVectorBytes || size < kJournalBytes) return std::nullopt;
  const auto* raw = static_cast<const std::byte*>(mapped);
  std::vector<Entry> entries;
  entries.reserve(stats.reserved);
  for (std::uint32_t i = 0; i < stats.reserved; ++i) {
    Entry entry{};
    std::memcpy(&entry, raw + std::size_t(i) * kEntryBytes, kEntryBytes);
    if (entry.tag != kTag || entry.address_complement != ~entry.guest_address ||
        entry.byte_count != kVectorBytes || (entry.guest_address % 4) != 0 ||
        std::size_t(entry.guest_address) > guest_shadow_size - kVectorBytes) {
      return std::nullopt;
    }
    entries.push_back(entry);
  }
  // Writes to overlapping locations from different vertex invocations have
  // no deterministic CPU-observed ordering. Never guess the winning value.
  std::vector<std::uint32_t> addresses;
  addresses.reserve(entries.size());
  for (const Entry& entry : entries) addresses.push_back(entry.guest_address);
  std::sort(addresses.begin(), addresses.end());
  for (std::size_t i = 1; i < addresses.size(); ++i) {
    if (std::uint64_t(addresses[i - 1]) + kVectorBytes > addresses[i])
      return std::nullopt;
  }
  return entries;
}

using Dirty = std::function<void(std::size_t, std::size_t)>;
// This adapter is callable ONLY by a backend which truly halted all guest
// threads and validated a contiguous physical-memory mapping; Plume53 does
// not have such a proven gate and deliberately never calls Commit().
inline bool Commit(const std::vector<Entry>& verified,
                   std::span<std::byte> exclusive_contiguous_physical,
                   bool guest_threads_exclusively_paused, const Dirty& dirty) {
  if (!guest_threads_exclusively_paused || !dirty || verified.empty()) return false;
  if (exclusive_contiguous_physical.size() < kVectorBytes) return false;
  for (const Entry& e : verified) {
    if (e.tag != kTag || e.address_complement != ~e.guest_address ||
        e.byte_count != kVectorBytes || (e.guest_address % 4) != 0 ||
        std::size_t(e.guest_address) > exclusive_contiguous_physical.size() - kVectorBytes)
      return false;
  }
  std::vector<std::uint32_t> offsets;
  for (const Entry& e : verified) offsets.push_back(e.guest_address);
  std::sort(offsets.begin(), offsets.end());
  for (std::size_t i = 1; i < offsets.size(); ++i) {
    if (std::uint64_t(offsets[i - 1]) + kVectorBytes > offsets[i]) return false;
  }
  for (const Entry& e : verified) {
    std::memcpy(exclusive_contiguous_physical.data() + e.guest_address,
                e.data, kVectorBytes);
  }
  for (const Entry& e : verified) dirty(e.guest_address, e.guest_address + kVectorBytes);
  return true;
}
}  // namespace fable2::memexport53
