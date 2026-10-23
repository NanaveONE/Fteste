#include "../port/gpu/fable_memexport_vulkan50.h"
#include <array>
#include <cassert>
#include <iostream>
#include <vector>
using namespace fable2;
int main() {
  const memexport47::Stream stream{16, 0, 4, 4, 0, 0, false};
  const std::array<std::byte, 4> bytes{std::byte{1},std::byte{2},std::byte{3},std::byte{4}};
  const memexport50::GpuReadback correct{stream, 1, bytes, true};
  std::array<std::byte, 128> guest{};
  int wait=0, invalidate=0, notifications=0;
  auto fence=[&]{++wait;return true;};
  auto visible=[&]{++invalidate;return true;};
  auto dirty=[&](std::size_t b,std::size_t e){++notifications;assert(b==20 && e==24);};
  memexport50::ReadbackBridge success;
  assert(success.Transfer(std::span(&correct,1), guest, true, fence, visible, dirty));
  assert(guest[20]==std::byte{1} && guest[23]==std::byte{4});
  assert(wait==1 && invalidate==1 && notifications==1);
  assert(!success.Transfer(std::span(&correct,1),guest,true,fence,visible,dirty));
  memexport50::ReadbackBridge fence_fail;
  auto fail=[] { return false; };
  assert(!fence_fail.Transfer(std::span(&correct,1),guest,true,fail,visible,dirty));
  assert(invalidate==1 && notifications==1);
  memexport50::ReadbackBridge invalidate_fail;
  assert(!invalidate_fail.Transfer(std::span(&correct,1),guest,true,fence,fail,dirty));
  assert(notifications==1);
  memexport50::ReadbackBridge exclusive_fail;
  assert(!exclusive_fail.Transfer(std::span(&correct,1),guest,false,fence,visible,dirty));
  memexport50::ReadbackBridge unsupported_format;
  const memexport50::GpuReadback bad{stream,1,bytes,false};
  assert(!unsupported_format.Transfer(std::span(&bad,1),guest,true,fence,visible,dirty));
  assert(notifications==1);
  memexport50::ReadbackBridge bad_entry;
  const memexport50::GpuReadback invalid{stream,4,bytes,true};
  assert(!bad_entry.Transfer(std::span(&invalid,1),guest,true,fence,visible,dirty));
  assert(notifications==1);
  std::cout << "PASS MemExport50: fence, noncoherent visibility, guest exclusion, exact-copy handoff\n";
}
