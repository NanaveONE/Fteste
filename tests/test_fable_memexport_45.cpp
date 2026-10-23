#include "../port/gpu/fable_memexport_45.h"
#include <cassert>
#include <cstdint>
#include <iostream>
using fable2::memexport::DecodeStream;
using fable2::memexport::BytesPerElement;
using fable2::memexport::PlanWrite;

static std::array<uint32_t, 4> Address(uint32_t byte_address, uint32_t index,
                                       uint32_t count, uint32_t format) {
  assert(byte_address % 4 == 0);
  return {0x40000000u | (byte_address >> 2),
          0x4B000000u | index,
          0x4B000000u | (format << 8),
          0x4B000000u | count};
}
int main() {
  // A 128-bit float4 stream: stride 16 bytes for each eM# write.
  auto stream = DecodeStream(Address(0x400u, 2, 8, 38));
  assert(stream && stream->base_byte_address == 0x400u);
  assert(stream->element_index == 2 && stream->element_count == 8);
  assert(stream->format == 38);
  auto m0 = PlanWrite(*stream, 0, 0x2000);
  auto m4 = PlanWrite(*stream, 4, 0x2000);
  assert(m0 && m0->guest_byte_address == 0x420 && m0->byte_count == 16);
  assert(m4 && m4->guest_byte_address == 0x460 && m4->byte_count == 16);
  assert(!PlanWrite(*stream, 5, 0x2000)); // Only eM0...eM4 exist
  assert(!PlanWrite(*stream, 4, 0x460));  // End of memory exactly at start
  assert(!PlanWrite(*stream, 4, 0));
  assert(!PlanWrite(*stream, 4, 1ull << 33));
  auto format8 = DecodeStream(Address(0x200, 1, 5, 2));
  assert(format8 && PlanWrite(*format8, 3, 0x1000)->guest_byte_address == 0x204);
  // Stream index count is a hard bound even if physical memory has room.
  assert(!PlanWrite(*format8, 4, 0x1000));
  // 64-bit float stream: eM1 offset must be +8, not +16.
  auto format64 = DecodeStream(Address(0x800, 0, 5, 37));
  assert(format64 && PlanWrite(*format64, 1, 0x1000)->guest_byte_address == 0x808);
  // Decode metadata, without guessing how to pack it.
  auto special = Address(0x100, 0, 6, 6);
  special[2] |= 3u | (2u << 16) | (1u << 19);
  auto metadata = DecodeStream(special);
  assert(metadata && metadata->endianness == 3 && metadata->number_format == 2);
  assert(metadata->red_blue_swap);
  // Bad flags, NaN/negative indices, malformed number exponent.
  auto bad = Address(0x100, 0, 6, 6);
  bad[0] = (bad[0] & 0x3FFFFFFFu) | 0x80000000u;
  assert(!DecodeStream(bad));
  bad = Address(0x100, 0, 6, 6);
  bad[1] |= 0x80000000u;
  assert(!DecodeStream(bad));
  bad = Address(0x100, 0, 6, 6);
  bad[3] = 0x4A800006u;
  assert(!DecodeStream(bad));
  bad = Address(0x100, 6, 6, 6);
  assert(!DecodeStream(bad));
  bad = Address(0x100, 0, 0, 6);
  assert(!DecodeStream(bad));
  // Overflow and unsupported format must never produce guest memory writes.
  auto out = DecodeStream(Address(0x1FFFFFFCu, 0, 5, 38));
  assert(out && !PlanWrite(*out, 0, 512ull << 20));
  auto unknown = DecodeStream(Address(0x100, 0, 5, 60));
  assert(unknown && !PlanWrite(*unknown, 0, 512ull << 20));
  assert(!BytesPerElement(60));
  std::cout << "PASS: MemExport 45 stream decoding, 1/4/8/16-byte strides and bounds\n";
}
