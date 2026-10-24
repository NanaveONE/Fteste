#pragma once
// Experimental MemExport60: ReXGlue PHYSICAL-memory mapping adapter.
// This does NOT implement or assume stop-the-world. Only an SDK-integrated
// coordinator that really parks every guest writer can authorize a commit.
// Stock ReXGlue/Plume does not supply that coordinator; NEVER synthesize one
// with a renderer-local mutex or individual XThread::Suspend calls.
#include "fable_memexport_guest55.h"
#include <rex/system/xmemory.h>

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace fable2::memexport60 {

inline constexpr std::string_view kPinnedRexSdkRevision =
    "3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b";
inline constexpr std::uint64_t kPhysicalRangeBytes = 0x20000000ull; // 512 MiB

// Implement this inside a trusted ReXGlue runtime integration, not Plume.
// Acquire must cover guest CPU/JIT, asynchronous writers, allocations,
// mappings, and cache invalidation for the complete critical section.
// Returning false MUST leave no partially suspended threads behind.
struct CertifiedGuestWorld {
  virtual ~CertifiedGuestWorld() = default;
  virtual bool IsVerifiedFor(std::string_view sdk_revision) const noexcept = 0;
  virtual bool AcquireAllWriters() = 0;
  virtual bool AllWritersQuiescent() const noexcept = 0;
  virtual void MarkPhysicalDirty(std::uint32_t physical_address,
                                 std::size_t bytes) noexcept = 0;
  virtual void ReleaseAllWriters() noexcept = 0;
  virtual memexport55::WireEncoding VerifiedEncoding() const noexcept = 0;
};

// Uses the REAL rex::memory::Memory::TranslatePhysical, never virtual_membase.
// A live physical heap range is additionally required; TranslatePhysical by
// itself only computes a pointer and does NOT establish whether it is mapped.
class RexPhysicalMemoryHost final : public memexport55::PhysicalMemoryHost {
 public:
  RexPhysicalMemoryHost(rex::memory::Memory* memory, CertifiedGuestWorld* guest_world)
      : memory_(memory), guest_world_(guest_world) {}
  RexPhysicalMemoryHost(const RexPhysicalMemoryHost&) = delete;
  RexPhysicalMemoryHost& operator=(const RexPhysicalMemoryHost&) = delete;
  ~RexPhysicalMemoryHost() override { ReleaseGlobalGuestExclusion(); }

  bool AcquireGlobalGuestExclusion() override {
    if (active_ || !memory_ || !guest_world_ ||
        !guest_world_->IsVerifiedFor(kPinnedRexSdkRevision)) return false;
    if (!guest_world_->AcquireAllWriters()) return false;
    if (!guest_world_->AllWritersQuiescent()) {
      guest_world_->ReleaseAllWriters();
      return false;
    }
    active_ = true;
    return true;
  }

  bool MapPhysicalWritable(std::uint32_t physical_address, std::size_t length,
                           std::byte** destination) override {
    if (destination) *destination = nullptr;
    if (!active_ || !destination || !memory_ || !guest_world_ ||
        !guest_world_->AllWritersQuiescent() || !length ||
        std::uint64_t(physical_address) >= kPhysicalRangeBytes ||
        std::uint64_t(length) > kPhysicalRangeBytes - physical_address)
      return false;
    // QueryRangeAccess checks every page and rejects unmapped / read-only
    // physical ranges. Addresses are offsets, not 0xA0000000 aliases.
    auto* physical_heap = memory_->GetPhysicalHeap();
    if (!physical_heap ||
        physical_heap->QueryRangeAccess(
            physical_address,
            std::uint32_t(std::uint64_t(physical_address) + length - 1)) !=
            rex::memory::PageAccess::kReadWrite)
      return false;
    auto* pointer = memory_->TranslatePhysical<std::uint8_t*>(physical_address);
    if (!pointer) return false;
    *destination = reinterpret_cast<std::byte*>(pointer);
    return true;
  }

  void NotifyPhysicalDirty(std::uint32_t physical_address,
                           std::size_t length) noexcept override {
    if (active_ && guest_world_) guest_world_->MarkPhysicalDirty(physical_address, length);
  }

  void ReleaseGlobalGuestExclusion() noexcept override {
    if (active_ && guest_world_) {
      active_ = false;
      guest_world_->ReleaseAllWriters();
    }
  }

  memexport55::WireEncoding VerifiedExportEncoding() const noexcept override {
    return guest_world_ && guest_world_->IsVerifiedFor(kPinnedRexSdkRevision)
               ? guest_world_->VerifiedEncoding() : memexport55::WireEncoding::Unknown;
  }

 private:
  rex::memory::Memory* memory_ = nullptr; // Never owns the runtime.
  CertifiedGuestWorld* guest_world_ = nullptr; // Never owns coordinator.
  bool active_ = false;
};

} // namespace fable2::memexport60
