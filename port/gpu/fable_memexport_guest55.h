#pragma once
// Public MemExport55: all-or-nothing physical-memory transaction.
// A caller MUST provide an honest stop-the-world implementation that excludes
// every guest CPU thread and every other guest writer during this call.
// There is NO built-in stop-world API in the presently integrated Plume backend;
// an absent host remains a hard failure, never a permissive fallback.
#include "fable_memexport_journal53.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <vector>

namespace fable2::memexport55 {

// Format/endianness must be verified against actual Xenos export control.
// The experimental 51/53 HLSL emits four bit-pattern u32s per export.
enum class WireEncoding {
  Unknown,
  GuestBigEndian32,  // 4 Xenos 32-bit words, MSB first in physical memory
  GuestLittleEndian32 // explicitly verified raw little-endian words
};

// Only trusted runtime integration may implement this interface. The methods
// are intentionally not replaced with a mutex inside the renderer: such a
// mutex does NOT stop the guest threads running in the ReXGlue SDK.
struct PhysicalMemoryHost {
  virtual ~PhysicalMemoryHost() = default;
  // Must suspend/park ALL guest execution threads and all physical-memory
  // producers, with a memory ordering barrier, before returning true.
  virtual bool AcquireGlobalGuestExclusion() = 0;
  // Return a writable, LIVE host pointer to the exact guest PHYSICAL range.
  // The range must stay writable/mapped until ReleaseGlobalGuestExclusion.
  virtual bool MapPhysicalWritable(std::uint32_t physical_address,
                                   std::size_t length,
                                   std::byte** destination) = 0;
  // Runs while guest execution is still stopped. Must not throw.
  virtual void NotifyPhysicalDirty(std::uint32_t physical_address,
                                   std::size_t length) noexcept = 0;
  // Always resume/release, even if preflight fails. Must not throw.
  virtual void ReleaseGlobalGuestExclusion() noexcept = 0;
  // Must certify the physical offset encoding AND the 4x32-bit export format.
  virtual WireEncoding VerifiedExportEncoding() const noexcept = 0;
};

struct Result {
  enum class Status {
    NoHost, FenceOrVisibilityMissing, InvalidJournal, UnknownEncoding,
    PauseFailed, PhysicalMappingFailed, Committed
  } status = Status::NoHost;
  std::size_t entries = 0;
  explicit operator bool() const noexcept { return status == Status::Committed; }
};

class ExclusiveSession {
 public:
  explicit ExclusiveSession(PhysicalMemoryHost& host) : host_(host), locked_(host.AcquireGlobalGuestExclusion()) {}
  ~ExclusiveSession() { if (locked_) host_.ReleaseGlobalGuestExclusion(); }
  ExclusiveSession(const ExclusiveSession&) = delete;
  ExclusiveSession& operator=(const ExclusiveSession&) = delete;
  bool active() const noexcept { return locked_; }
 private:
  PhysicalMemoryHost& host_;
  bool locked_;
};

inline void EncodeWords(const memexport53::Entry& entry, WireEncoding mode,
                        std::array<std::byte, 16>& bytes) {
  for (std::size_t i = 0; i < 4; ++i) {
    std::uint32_t value = entry.data[i];
    for (unsigned shift = 0; shift < 4; ++shift) {
      const unsigned lane = mode == WireEncoding::GuestBigEndian32 ? 3u - shift : shift;
      bytes[i * 4 + lane] = static_cast<std::byte>((value >> (shift * 8)) & 0xffu);
    }
  }
}

// All journal validation, address checks, guest quiescence and pointer mapping
// happen BEFORE the first byte of guest memory is modified. GPU completion
// proof must come from the real Plume swapchain fence, not a caller guess.
inline Result CommitFencedJournal(
    const void* journal, std::size_t journal_bytes,
    const memexport52::Stats& stats,
    bool gpu_submission_fence_completed,
    bool coherent_memory_visible,
    PhysicalMemoryHost* host,
    std::size_t guest_shadow_bytes = memexport52::kGuestShadowBytes) {
  if (!host) return {Result::Status::NoHost, 0};
  if (!gpu_submission_fence_completed || !coherent_memory_visible)
    return {Result::Status::FenceOrVisibilityMissing, 0};
  const auto verified = memexport53::Validate(
      journal, journal_bytes, stats, true, true, guest_shadow_bytes);
  if (!verified || verified->empty())
    return {Result::Status::InvalidJournal, 0};
  const WireEncoding mode = host->VerifiedExportEncoding();
  if (mode != WireEncoding::GuestBigEndian32 &&
      mode != WireEncoding::GuestLittleEndian32)
    return {Result::Status::UnknownEncoding, verified->size()};

  ExclusiveSession pause(*host);
  if (!pause.active())
    return {Result::Status::PauseFailed, verified->size()};

  struct Pending {
    std::byte* destination = nullptr;
    std::uint32_t physical_address = 0;
    std::array<std::byte, 16> bytes{};
  };
  std::vector<Pending> pending;
  pending.reserve(verified->size());
  for (const auto& entry : *verified) {
    std::byte* destination = nullptr;
    if (!host->MapPhysicalWritable(entry.guest_address, memexport53::kVectorBytes,
                                    &destination) || !destination)
      return {Result::Status::PhysicalMappingFailed, verified->size()};
    Pending write{};
    write.destination = destination;
    write.physical_address = entry.guest_address;
    EncodeWords(entry, mode, write.bytes);
    pending.push_back(write);
  }
  // No failing operations between first memcpy and last dirty notification.
  for (const auto& write : pending)
    std::memcpy(write.destination, write.bytes.data(), write.bytes.size());
  for (const auto& write : pending)
    host->NotifyPhysicalDirty(write.physical_address, write.bytes.size());
  return {Result::Status::Committed, pending.size()};
}

} // namespace fable2::memexport55
