#include "../port/gpu/fable_memexport_sync_49.h"
#include <array>
#include <cassert>
#include <iostream>
#include <vector>
using namespace fable2;
int main(){
  std::array<std::byte,256> memory{};
  memexport47::Stream s{16, 1, 10, 4, 0, 0, false};
  const std::array<std::byte,4> bytes{std::byte{0x11},std::byte{0x22},std::byte{0x33},std::byte{0x44}};
  memexport49::ReadbackBatch batch;
  int events=0;
  auto dirty=[&](std::size_t a,std::size_t b){assert(a==20&&b==24);++events;};
  assert(batch.Record(s,0,bytes));
  assert(!batch.Commit(memory,true,dirty));  // cannot write before fence
  assert(batch.Submit());
  assert(!batch.Record(s,1,bytes));  // immutable after submission
  assert(!batch.Commit(memory,true,dirty));
  assert(batch.CompleteAfterFence(true,true));
  assert(!batch.Commit(memory,false,dirty)); // no exclusive ownership
  assert(memory[20]==std::byte{0});
  assert(batch.Commit(memory,true,dirty));
  assert(memory[20]==std::byte{0x11});
  assert(events==1);
  assert(!batch.Commit(memory,true,dirty));
  memexport49::ReadbackBatch bad_fence;
  assert(bad_fence.Record(s,0,bytes)&&bad_fence.Submit());
  assert(!bad_fence.CompleteAfterFence(false,true));
  assert(!bad_fence.Commit(memory,true,dirty));
  memexport49::ReadbackBatch bad_range;
  auto far=s;far.base_address=248;far.first_index=0;
  assert(bad_range.Record(far,0,bytes)&&bad_range.Submit());
  assert(bad_range.CompleteAfterFence(true,true));
  assert(bad_range.Commit(memory,true,[](std::size_t,std::size_t){}));
  memexport49::ReadbackBatch fail_atomic;
  assert(fail_atomic.Record(s,0,bytes));
  auto out=s;out.base_address=252;out.first_index=1;
  assert(fail_atomic.Record(out,0,bytes));
  assert(fail_atomic.Submit()&&fail_atomic.CompleteAfterFence(true,true));
  std::array<std::byte,32> small{};
  assert(!fail_atomic.Commit(small,true,dirty));
  assert(small[20]==std::byte{0});
  std::cout<<"PASS MemExport49: fail-closed readback fence, exclusivity, ranges and dirty notification\n";
}
