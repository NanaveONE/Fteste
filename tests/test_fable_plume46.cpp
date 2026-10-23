#include "../port/gpu/fable_loop_constants_46.h"
#include <array>
#include <cassert>
#include <iostream>
#include <cstdint>
int main() {
  std::array<std::uint32_t, 32> guest{};
  // loop count 8, aL start 5, signed step -2
  guest[0] = 8u | (5u << 8) | (0xFEu << 16);
  guest[16] = 255u | (200u << 8) | (1u << 16);
  auto v = fable2::plume46::DecodeLoopConstants(guest.data());
  assert(v[0][0] == 8 && v[0][1] == 5 && v[0][2] == -2);
  assert(v[16][0] == 255 && v[16][1] == 200 && v[16][2] == 1);
  assert(v[31][0] == 0 && v[31][1] == 0 && v[31][2] == 0);
  assert(fable2::plume46::kUploadBytes == 512u);
  std::cout << "PASS: 46 real SQ loop constant packing and Vulkan binding7 payload\n";
}
