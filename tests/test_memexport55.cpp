#include "../port/gpu/fable_memexport_guest55.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

using namespace fable2::memexport55;
using namespace fable2::memexport53;
using fable2::memexport52::Stats;

struct TestHost : PhysicalMemoryHost {
  std::array<std::byte, 256> ram{};
  bool can_lock = true;
  bool locked = false;
  bool deny_address_128 = false;
  unsigned acquired = 0, released = 0, dirty_count = 0;
  WireEncoding encoding = WireEncoding::GuestBigEndian32;
  bool AcquireGlobalGuestExclusion() override {
    ++acquired;
    if (!can_lock || locked) return false;
    locked = true; return true;
  }
  bool MapPhysicalWritable(std::uint32_t offset, std::size_t len,
                           std::byte** dest) override {
    assert(locked);
    if (offset == 128 && deny_address_128) return false;
    if (offset > ram.size() || len > ram.size() - offset) return false;
    *dest = ram.data() + offset; return true;
  }
  void NotifyPhysicalDirty(std::uint32_t offset, std::size_t size) noexcept override {
    assert(locked && size == 16 && offset < ram.size()); ++dirty_count;
  }
  void ReleaseGlobalGuestExclusion() noexcept override {
    assert(locked); locked = false; ++released;
  }
  WireEncoding VerifiedExportEncoding() const noexcept override { return encoding; }
};

int main() {
  std::vector<std::byte> journal(kJournalBytes);
  Entry a{};
  a.guest_address = 64; a.byte_count = 16;
  a.data[0] = 0x12345678; a.data[1] = 0x3F800000;
  a.data[2] = 0xFFFFFFFF; a.data[3] = 0;
  a.tag = kTag; a.address_complement = ~a.guest_address;
  Entry b = a;
  b.guest_address = 128; b.address_complement = ~b.guest_address;
  std::memcpy(journal.data(), &a, sizeof(a));
  std::memcpy(journal.data() + sizeof(a), &b, sizeof(b));
  Stats stats{}; stats.reserved = stats.stored_vectors = 2;
  TestHost host;
  auto run = [&](bool fence = true, bool coherent = true) {
    return CommitFencedJournal(journal.data(),journal.size(),stats,
                               fence,coherent,&host,host.ram.size());
  };
  assert(CommitFencedJournal(journal.data(),journal.size(),stats,true,true,nullptr,host.ram.size()).status == Result::Status::NoHost);
  assert(run(false).status == Result::Status::FenceOrVisibilityMissing);
  assert(run(true,false).status == Result::Status::FenceOrVisibilityMissing);
  assert(host.acquired == 0 && host.ram[64] == std::byte{});
  stats.invalid_address=1;
  assert(run().status == Result::Status::InvalidJournal);
  stats.invalid_address=0;
  host.encoding=WireEncoding::Unknown;
  assert(run().status == Result::Status::UnknownEncoding);
  assert(host.acquired == 0);
  host.encoding=WireEncoding::GuestBigEndian32;
  host.can_lock=false;
  assert(run().status == Result::Status::PauseFailed);
  assert(!host.locked && host.released == 0);
  host.can_lock=true;
  host.deny_address_128=true;
  assert(run().status == Result::Status::PhysicalMappingFailed);
  assert(host.ram[64] == std::byte{} && !host.locked && host.released == 1 && host.dirty_count == 0);
  host.deny_address_128=false;
  assert(run().status == Result::Status::Committed);
  assert(host.ram[64] == std::byte{0x12} && host.ram[65] == std::byte{0x34} &&
         host.ram[66] == std::byte{0x56} && host.ram[67] == std::byte{0x78});
  assert(host.ram[128] == std::byte{0x12} && host.dirty_count==2);
  assert(!host.locked && host.released == 2);
  // Little-endian payload only when a separate backend certifies it.
  host.encoding=WireEncoding::GuestLittleEndian32;
  host.ram[64]=std::byte{};
  assert(run().status == Result::Status::Committed);
  assert(host.ram[64] == std::byte{0x78} && host.ram[67] == std::byte{0x12});
  // Overlap must never acquire the guest lock nor modify RAM.
  b.guest_address=72; b.address_complement=~b.guest_address;
  std::memcpy(journal.data()+sizeof(a),&b,sizeof(b));
  auto old=host.ram;
  unsigned n=host.acquired;
  assert(run().status == Result::Status::InvalidJournal);
  assert(host.acquired==n && host.ram==old);
  std::cout << "PASS MemExport55: strict fence, validated layout, exclusive atomic preflight, endian, release\n";
}
