#include "../port/gpu/fable_memexport52.h"
#include <array>
#include <cassert>
#include <cstring>
#include <iostream>
using namespace fable2::memexport52;
int main() {
  static_assert(kMemoryDescriptorIndex == 68);
  static_assert(kStatsDescriptorIndex == 69);
  Stats s{1,2,3,0};
  std::array<std::byte,kStatsBytes> bytes{};
  std::memcpy(bytes.data(), &s, bytes.size());
  assert(!ReadStatsAfterFence(bytes.data(),bytes.size(),false,true));
  assert(!ReadStatsAfterFence(bytes.data(),bytes.size(),true,false));
  assert(!ReadStatsAfterFence(bytes.data(),bytes.size()-1,true,true));
  const auto x=ReadStatsAfterFence(bytes.data(),bytes.size(),true,true);
  assert(x && x->unsupported_format == 1 && x->stored_vectors == 3);
  assert(!MayCommitGuest(*x,true,true,true));
  Stats good{0,0,1,0};
  assert(!MayCommitGuest(good,false,true,true));
  assert(!MayCommitGuest(good,true,false,true));
  assert(!MayCommitGuest(good,true,true,false));
  assert(MayCommitGuest(good,true,true,true));
  std::cout << "PASS MemExport52: descriptors, fence/visibility, and fail-closed host commit\n";
}
