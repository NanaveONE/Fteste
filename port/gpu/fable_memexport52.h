#pragma once
// Fable II 52: host-visible GPU-side MemExport telemetry. The Vulkan resources
// are allocated by Plume. This header is intentionally independent of Vulkan
// so the recorded statistics and safety gates can be tested on desktop.
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>

namespace fable2::memexport52 {
constexpr std::size_t kGuestShadowBytes = 64u * 1024u * 1024u;
constexpr std::size_t kStatsBytes = 16;
constexpr unsigned kMemoryBinding = 8;
constexpr unsigned kStatsBinding = 9;
// Plume's builder creates three CB descriptors, 64 texture/sampler entries,
// and then one dynamic loop CB (binding7): the next descriptor indices are 68,69.
constexpr unsigned kMemoryDescriptorIndex = 3 + 4 * 16 + 1;
constexpr unsigned kStatsDescriptorIndex = kMemoryDescriptorIndex + 1;
struct Stats {
  std::uint32_t unsupported_format = 0;
  std::uint32_t invalid_address = 0;
  std::uint32_t stored_vectors = 0;
  std::uint32_t reserved = 0;
};
static_assert(sizeof(Stats) == kStatsBytes);
inline std::optional<Stats> ReadStatsAfterFence(const void* mapped,
                                                std::size_t size,
                                                bool fence_completed,
                                                bool host_coherent) {
  if (!mapped || size < kStatsBytes || !fence_completed || !host_coherent)
    return std::nullopt;
  Stats stats;
  std::memcpy(&stats, mapped, kStatsBytes);
  return stats;
}
inline bool MayCommitGuest(const Stats& stats, bool guest_locked,
                            bool verified_export_journal,
                            bool ranges_converted) {
  // This patch deliberately has no journal or guest memory exclusion protocol.
  // Merely binding the Vulkan buffers MUST NOT license copying arbitrary RAM.
  return guest_locked && verified_export_journal && ranges_converted &&
         stats.unsupported_format == 0 && stats.invalid_address == 0;
}
} // namespace fable2::memexport52
