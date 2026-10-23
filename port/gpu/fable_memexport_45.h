// Fable II / Xbox 360 Xenos MemExport -- bounded address planning only.
// No proprietary game data. Does NOT issue Vulkan storage writes.
// Wire format cross-checked against xenia-project/xenia src/xenia/gpu/xenos.h
// (xe_gpu_memexport_stream_t, Xbox 360 Xenos stream constant).
#pragma once

#include <array>
#include <cstdint>
#include <optional>

namespace fable2::memexport {

// The four 32-bit *bit patterns* in eA.xyzw (use bit_cast/asuint, never a
// numeric float->uint conversion: the Xenos deliberately packs integers in
// IEEE-754 mantissas).
using ExportAddress = std::array<std::uint32_t, 4>;

struct Stream {
  std::uint32_t base_byte_address = 0;
  std::uint32_t element_count = 0;
  std::uint32_t element_index = 0;
  std::uint8_t format = 0;
  std::uint8_t endianness = 0;
  std::uint8_t number_format = 0;
  bool red_blue_swap = false;
};

struct Write {
  std::uint32_t guest_byte_address = 0;
  std::uint32_t byte_count = 0;
  std::uint32_t element_index = 0;
};

// Deliberately reject malformed stream constants, including exponent/sign
// corruption (Xenos drops such writes instead of treating floats numerically).
inline std::optional<Stream> DecodeStream(const ExportAddress& a) {
  constexpr std::uint32_t kPackedExponent23 = 0x4B000000u;
  // X in this stream format is 0b01 in its top two bits plus a 30-bit
  // dword base; Y, Z, W carry 2^23 float-exponent encodings.
  if ((a[0] >> 30) != 1u || (a[1] & 0xFF800000u) != kPackedExponent23 ||
      (a[2] >> 20) != 0x4B0u || (a[3] & 0xFF800000u) != kPackedExponent23) {
    return std::nullopt;
  }
  Stream out;
  out.base_byte_address = (a[0] & 0x3FFFFFFFu) << 2;
  out.element_index = a[1] & 0x007FFFFFu;
  out.element_count = a[3] & 0x007FFFFFu;
  out.endianness = static_cast<std::uint8_t>(a[2] & 7u);
  out.format = static_cast<std::uint8_t>((a[2] >> 8) & 63u);
  out.number_format = static_cast<std::uint8_t>((a[2] >> 16) & 7u);
  out.red_blue_swap = ((a[2] >> 19) & 1u) != 0;
  // eA encodings where the GPU treats the index as invalid produce no writes.
  if (out.element_count == 0 || out.element_index >= out.element_count) {
    return std::nullopt;
  }
  return out;
}

// Address sizes from Xenos ColorFormat -- ONLY supported ordinary linear
// formats. More exotic color formats must be implemented with exact packing,
// not assigned an incorrect element stride.
inline std::optional<std::uint32_t> BytesPerElement(std::uint8_t f) {
  switch (f) {
    case 2: case 8: case 9: return 1;       // 8, 8_A, 8_B
    case 3: case 4: case 5: case 10: case 15:
    case 24: case 30: return 2;             // 16-bit packed, 16_FLOAT
    case 6: case 7: case 14: case 16: case 17:
    case 25: case 31: case 36: return 4;   // 32-bit formats
    case 26: case 32: case 37: return 8;   // 64-bit formats
    case 38: return 16;                    // 32_32_32_32_FLOAT
    default: return std::nullopt;
  }
}

// eM0..eM4 map to consecutive elements of the stream, not 16-byte blocks.
// guest_memory_bytes must reflect the *actual* configured guest allocation;
// it is NOT inferred from the address and cannot exceed the 512-MiB physical
// memory of Xbox 360. All calculations use 64-bit intermediates.
inline std::optional<Write> PlanWrite(const Stream& stream,
                                     unsigned em_index,
                                     std::uint64_t guest_memory_bytes) {
  if (em_index > 4 || stream.element_index >= stream.element_count ||
      guest_memory_bytes == 0 || guest_memory_bytes > (512ull << 20)) {
    return std::nullopt;
  }
  const auto size = BytesPerElement(stream.format);
  if (!size) return std::nullopt;
  const std::uint64_t index = std::uint64_t(stream.element_index) + em_index;
  if (index >= stream.element_count) return std::nullopt;
  const std::uint64_t offset = std::uint64_t(stream.base_byte_address) + index * *size;
  if (offset > guest_memory_bytes || *size > guest_memory_bytes - offset) {
    return std::nullopt;
  }
  // The first 512 MiB are addressable with 29 bits, so successful range checks
  // also ensure safe narrowing back to u32.
  return Write{static_cast<std::uint32_t>(offset), *size,
               static_cast<std::uint32_t>(index)};
}

// IMPORTANT: This is only a decoder / bounds planner. Actual eA/eM
// predication, stream flushes, number-format packing, endian/channel swaps,
// GPU storage writes and CPU-visible synchronization remain to implement.
}  // namespace fable2::memexport
