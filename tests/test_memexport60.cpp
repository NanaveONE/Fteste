#include "../port/gpu/fable_memexport_rex60.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

namespace e55 = fable2::memexport55;
namespace e53 = fable2::memexport53;
using fable2::memexport60::CertifiedGuestWorld;
using fable2::memexport60::RexPhysicalMemoryHost;

struct World final : CertifiedGuestWorld {
  bool certified = false, can_pause = true, quiescent = true, paused = false;
  unsigned starts = 0, finishes = 0, dirty = 0;
  e55::WireEncoding mode = e55::WireEncoding::GuestBigEndian32;
  bool IsVerifiedFor(std::string_view revision) const noexcept override {
    return certified && revision == fable2::memexport60::kPinnedRexSdkRevision;
  }
  bool AcquireAllWriters() override {
    ++starts;
    if (!can_pause) return false;
    assert(!paused);
    paused = true;
    return true;
  }
  bool AllWritersQuiescent() const noexcept override { return paused && quiescent; }
  void MarkPhysicalDirty(std::uint32_t address, std::size_t length) noexcept override {
    assert(paused && address == 32 && length == 16);
    ++dirty;
  }
  void ReleaseAllWriters() noexcept override {
    assert(paused);
    paused = false;
    ++finishes;
  }
  e55::WireEncoding VerifiedEncoding() const noexcept override { return mode; }
};

int main() {
  rex::memory::Memory memory;
  memory.heap.allowed_end_exclusive = 256;
  memory.heap.access = rex::memory::PageAccess::kReadWrite;
  World world;
  RexPhysicalMemoryHost host(&memory, &world);
  std::vector<std::byte> journal(e53::kJournalBytes);
  e53::Entry entry{};
  entry.guest_address = 32;
  entry.byte_count = 16;
  entry.tag = e53::kTag;
  entry.address_complement = ~entry.guest_address;
  entry.data[0] = 0x12345678u;
  std::memcpy(journal.data(), &entry, sizeof(entry));
  fable2::memexport52::Stats stats{};
  stats.reserved = 1;
  stats.stored_vectors = 1;
  auto commit = [&] {
    return e55::CommitFencedJournal(journal.data(), journal.size(), stats,
                                    true, true, &host, memory.bytes.size());
  };
  assert(commit().status == e55::Result::Status::UnknownEncoding);
  assert(world.starts == 0 && world.dirty == 0);
  world.certified = true;
  world.can_pause = false;
  assert(commit().status == e55::Result::Status::PauseFailed);
  assert(world.starts == 1 && world.finishes == 0);
  world.can_pause = true;
  world.quiescent = false;
  assert(commit().status == e55::Result::Status::PauseFailed);
  assert(world.starts == 2 && world.finishes == 1 && !world.paused);
  world.quiescent = true;
  memory.heap.access = rex::memory::PageAccess::kReadOnly;
  assert(commit().status == e55::Result::Status::PhysicalMappingFailed);
  assert(!world.paused && world.dirty == 0 && memory.bytes[32] == 0);
  memory.heap.access = rex::memory::PageAccess::kReadWrite;
  memory.heap.allowed_end_exclusive = 40;
  assert(commit().status == e55::Result::Status::PhysicalMappingFailed);
  memory.heap.allowed_end_exclusive = 256;
  std::byte* dst = reinterpret_cast<std::byte*>(1);
  assert(!host.MapPhysicalWritable(32, 16, &dst) && dst == nullptr);
  assert(commit().status == e55::Result::Status::Committed);
  assert(world.dirty == 1 && !world.paused && world.finishes == 4);
  assert(memory.bytes[32] == 0x12 && memory.bytes[33] == 0x34 &&
         memory.bytes[34] == 0x56 && memory.bytes[35] == 0x78);
  assert(host.AcquireGlobalGuestExclusion()); // certified gate may acquire
  assert(!host.AcquireGlobalGuestExclusion()); // no recursive acquire
  assert(!host.MapPhysicalWritable(0x20000000u, 16, &dst));
  assert(!host.MapPhysicalWritable(0x1FFFFFFFu, 16, &dst));
  assert(!host.MapPhysicalWritable(0, 0, &dst));
  assert(host.MapPhysicalWritable(32, 16, &dst));
  world.quiescent = false;
  assert(!host.MapPhysicalWritable(32, 16, &dst));
  world.quiescent = true;
  host.ReleaseGlobalGuestExclusion();
  host.ReleaseGlobalGuestExclusion();
  assert(world.finishes == 5);
  std::cout << "PASS: MemExport60 maps real physical offsets only behind certified full writer exclusion\n";
}
