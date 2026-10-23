#pragma once
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

// Guest Xenos SQ loop constants: 32 packed dwords in register window 0x4908.
// Loop count [7:0], start aL [15:8], signed step [23:16].
// Runtime XenosRecomp patch 42 consumes int4 g_IntegerShaderConstants[32]
// at set 0, binding 7; iN.x controls the iteration count.
namespace fable2::plume46 {
constexpr std::size_t kLoopRegisters = 32;
constexpr std::size_t kComponents = 4;
constexpr std::size_t kUploadBytes = kLoopRegisters * kComponents * sizeof(std::int32_t);
using LoopBank = std::array<std::array<std::int32_t, kComponents>, kLoopRegisters>;

inline LoopBank DecodeLoopConstants(const std::uint32_t* guest_words) noexcept {
  LoopBank out{};
  for (std::size_t i = 0; i != kLoopRegisters; ++i) {
    const std::uint32_t w = guest_words[i];
    out[i][0] = static_cast<std::int32_t>(w & 0xFFu);
    out[i][1] = static_cast<std::int32_t>((w >> 8) & 0xFFu);
    const std::uint32_t step = (w >> 16) & 0xFFu;
    out[i][2] = step < 128u ? static_cast<std::int32_t>(step)
                               : static_cast<std::int32_t>(step) - 256;
    // For future translator support: full packed register in .w.
    out[i][3] = std::bit_cast<std::int32_t>(w);
  }
  return out;
}
static_assert(sizeof(LoopBank) == kUploadBytes);
}  // namespace fable2::plume46
