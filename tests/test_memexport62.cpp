#include "../port/sdk/fable_memexport_sdk62.h"
#include <cassert>
#include <cstdint>
#include <thread>
#include <atomic>
#include <iostream>
#include <vector>

using namespace fable2::memexport62;
int main() {
  auto before = Audit().Read();
  assert(!before.globally_exclusive_verified);
  assert(!Audit().EveryMemoryWriterIsInstrumented());
  std::atomic<unsigned> entered{0};
  std::atomic<bool> release{false};
  std::vector<std::thread> workers;
  for (int i = 0; i < 4; ++i) {
    workers.emplace_back([&]() {
      WriterScope guest(WriterPath::GuestExecute);
      {
        WriterScope copy(WriterPath::MemoryCopy, 16);
        WriterScope fill(WriterPath::MemoryFill, 8);
      }
      entered.fetch_add(1, std::memory_order_release);
      while (!release.load(std::memory_order_acquire)) std::this_thread::yield();
    });
  }
  while (entered.load(std::memory_order_acquire) != 4) std::this_thread::yield();
  auto active = Audit().Read();
  assert(active.active_guest_executors == 4);
  assert(active.active_memory_helpers == 0);
  assert(active.peak_guest_executors >= 4);
  assert(active.guest_entries == before.guest_entries + 4);
  assert(active.memory_helpers == before.memory_helpers + 8);
  assert(active.helper_bytes == before.helper_bytes + 96);
  // Even when all current writers leave, full guest writer coverage is false.
  release.store(true, std::memory_order_release);
  for (auto& t : workers) t.join();
  auto after = Audit().Read();
  assert(after.active_guest_executors == 0 && after.active_memory_helpers == 0);
  assert(!after.globally_exclusive_verified);
  assert(!Audit().EveryMemoryWriterIsInstrumented());
  std::cout << "PASS MemExport62: real threaded scopes, activity counters, no false certification\n";
}
