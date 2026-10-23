#include "../port/gpu/fable_memexport_journal53.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <span>
#include <vector>
using namespace fable2::memexport53;
using fable2::memexport52::Stats;

int main() {
  static_assert(kJournalDescriptorIndex == 70);
  std::vector<std::byte> data(kJournalBytes);
  Entry e{};
  e.guest_address = 128;
  e.byte_count = 16;
  e.data[0] = 0x3F800000;
  e.data[1] = 0x40000000;
  e.data[2] = 0x40400000;
  e.data[3] = 0x40800000;
  e.tag = kTag;
  e.address_complement = ~e.guest_address;
  std::memcpy(data.data(), &e, sizeof(e));
  Stats stats{};
  stats.reserved = stats.stored_vectors = 1;
  assert(!Validate(data.data(), data.size(), stats, false, true, 1024));
  assert(!Validate(data.data(), data.size(), stats, true, false, 1024));
  assert(!Validate(data.data(), data.size()-1, stats, true, true, 1024));
  auto entries = Validate(data.data(), data.size(), stats, true, true, 1024);
  assert(entries && entries->size()==1 && (*entries)[0].guest_address==128);
  std::array<std::byte,256> guest{};
  bool notified = false;
  auto dirty = [&](std::size_t start, std::size_t end){
    assert(start==128 && end==144); notified=true;
  };
  assert(!Commit(*entries,guest,false,dirty));
  assert(!notified && guest[128]==std::byte{});
  assert(Commit(*entries,guest,true,dirty));
  assert(notified);
  std::array<std::byte, 16> expected{};
  std::memcpy(expected.data(),e.data,16);
  assert(std::memcmp(guest.data()+128,expected.data(),16)==0);
  stats.unsupported_format=1;
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  stats.unsupported_format=0; stats.invalid_address=1;
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  stats.invalid_address=0;stats.stored_vectors=0;
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  stats.stored_vectors=1;stats.reserved=kCapacity+1;
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  stats.reserved=stats.stored_vectors=2;
  std::memcpy(data.data()+32,&e,32);
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  stats.reserved=stats.stored_vectors=1;
  e.tag=0;
  std::memcpy(data.data(),&e,32);
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  e.tag=kTag;e.guest_address=0xFFFFFFFCu;e.address_complement=~e.guest_address;
  std::memcpy(data.data(),&e,32);
  assert(!Validate(data.data(),data.size(),stats,true,true,1024));
  std::cout << "PASS MemExport53: verified GPU journal, bounds, overlap, fence, exclusive commit\n";
}
