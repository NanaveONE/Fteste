#include "../port/gpu/fable_memexport_world61.h"

#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
namespace m53 = fable2::memexport53;
namespace m55 = fable2::memexport55;
namespace m60 = fable2::memexport60;
namespace m61 = fable2::memexport61;

struct TestProof final : m61::CoverageProof {
  std::atomic<bool> covered{false};
  std::atomic<unsigned> notifications{0};
  bool EveryMemoryWriterIsInstrumented() const noexcept override {
    return covered.load(std::memory_order_acquire);
  }
  m55::WireEncoding CertifiedXenosEncoding() const noexcept override {
    return m55::WireEncoding::GuestBigEndian32;
  }
  void InvalidatePhysicalCaches(std::uint32_t address, std::size_t length) noexcept override {
    assert(address == 32 && length == 16);
    ++notifications;
    // The newcomer must NOT be able to enter while dirty callbacks are running.
    std::this_thread::sleep_for(25ms);
  }
};

int main() {
  rex::memory::Memory memory;
  memory.heap.allowed_end_exclusive = 256;
  memory.heap.access = rex::memory::PageAccess::kReadWrite;
  TestProof proof;
  m61::CooperativeWorld world(&proof, 100ms);
  m60::RexPhysicalMemoryHost host(&memory, &world);
  std::vector<std::byte> journal(m53::kJournalBytes);
  m53::Entry entry{};
  entry.guest_address = 32;
  entry.byte_count = 16;
  entry.tag = m53::kTag;
  entry.address_complement = ~entry.guest_address;
  entry.data[0] = 0x12345678u;
  std::memcpy(journal.data(), &entry, sizeof(entry));
  fable2::memexport52::Stats stats{};
  stats.reserved = 1;
  stats.stored_vectors = 1;
  auto commit = [&] {
    return m55::CommitFencedJournal(journal.data(), journal.size(), stats,
                                    true, true, &host, memory.bytes.size());
  };

  // Stock SDK has no certified coverage; absolutely no writes permitted.
  assert(!world.IsVerifiedFor(m60::kPinnedRexSdkRevision));
  assert(!world.IsVerifiedFor("wrong-SDK"));
  assert(commit().status == m55::Result::Status::UnknownEncoding);
  assert(memory.bytes[32] == 0u && proof.notifications == 0);

  // Simulate a FULLY instrumented runtime, only for this test.
  proof.covered = true;
  assert(world.IsVerifiedFor(m60::kPinnedRexSdkRevision));
  // Holding an active guest writer must cause a bounded timeout without RAM write.
  auto current = world.EnterWriter(m61::WriterClass::GuestExecutor);
  assert(current);
  assert(commit().status == m55::Result::Status::PauseFailed);
  assert(!world.PauseRequested());
  assert(memory.bytes[32] == 0u && proof.notifications == 0);
  current.Reset();

  auto producer = world.EnterWriter(m61::WriterClass::HostProducer);
  assert(producer);
  std::atomic<bool> commit_done{false};
  std::atomic<bool> entrant_entered{false};
  m55::Result::Status final_status = m55::Result::Status::NoHost;
  std::thread submit([&] {
    final_status = commit().status;
    commit_done.store(true, std::memory_order_release);
  });
  for (int i = 0; i < 1000 && !world.PauseRequested(); ++i)
    std::this_thread::sleep_for(1ms);
  assert(world.PauseRequested());
  std::thread newcomer([&] {
    auto writer = world.EnterWriter(m61::WriterClass::KernelAndJit);
    assert(writer);
    entrant_entered.store(true, std::memory_order_release);
  });
  std::this_thread::sleep_for(5ms);
  assert(!entrant_entered.load(std::memory_order_acquire));
  assert(memory.bytes[32] == 0u);
  producer.Reset();
  submit.join();
  newcomer.join();
  assert(final_status == m55::Result::Status::Committed);
  assert(commit_done && entrant_entered);
  assert(proof.notifications == 1);
  assert(memory.bytes[32] == 0x12u && memory.bytes[33] == 0x34u);
  assert(memory.bytes[34] == 0x56u && memory.bytes[35] == 0x78u);

  // Runtime loses coverage certification: no further guest commits allowed.
  proof.covered = false;
  assert(commit().status == m55::Result::Status::UnknownEncoding);
  assert(proof.notifications == 1);
  world.Close();
  assert(!world.EnterWriter(m61::WriterClass::MappingOrInvalidator));
  assert(!world.AcquireAllWriters());
  std::cout << "PASS MemExport61: cooperative guest/producer gate, timeout, "
               "new-writer exclusion, real journal and strict coverage proof\n";
}
