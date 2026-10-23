#include "../port/gpu/fable_memexport_writer_47.h"
#include <array>
#include <cassert>
#include <iostream>
using namespace fable2::memexport47;
int main() {
  std::array<std::byte, 256> mem{};
  MemoryWriter writer{std::span<std::byte>(mem)};
  Stream s{32, 2, 6, 4, 0, 0, false};
  std::array<std::byte,4> payload{std::byte{1},std::byte{2},std::byte{3},std::byte{4}};
  assert(writer.Store(s,0,payload));
  assert(mem[40]==std::byte{1} && mem[43]==std::byte{4});
  assert(writer.Store(s,1,payload));
  assert(writer.dirty().size()==1 && writer.dirty()[0].begin==40 && writer.dirty()[0].end==48);
  assert(!writer.Store(s,4,payload));  // outside declared stream
  assert(writer.dirty().size()==1);
  s.endian=1;
  assert(!writer.Store(s,0,payload));  // unsupported endianness: no bogus write
  s.endian=0; s.red_blue_swap=true;
  assert(!writer.Store(s,0,payload));
  s.red_blue_swap=false; s.number_format=1;
  assert(!writer.Store(s,0,payload));
  s.number_format=0;
  assert(!writer.Store(s,0,std::span<const std::byte>(payload.data(),2)));
  s.base_address=250; s.first_index=0;
  assert(!writer.Store(s,2,payload));
  s.base_address=32; s.first_index=0; s.element_count=5;
  assert(writer.Store(s,4,payload));
  assert(writer.dirty().size()==1 && writer.dirty()[0].end==52);
  writer.ClearDirtyAfterHostSync();
  assert(writer.dirty().empty());
  std::cout << "PASS: MemExport47 checked CPU writes and dirty-range tracking\n";
}
