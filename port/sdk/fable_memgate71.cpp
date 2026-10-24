#include "fable_memgate71.h"
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <thread>

namespace {
struct World {
  std::mutex mutex;
  std::condition_variable cv;
  std::array<uint64_t, FABLE_M71_KIND_COUNT> entries{};
  uint64_t active_outer = 0;
  uint64_t drains = 0;
  uint64_t waiting_entries = 0;
  bool requested = false;
  bool exclusive = false;
  std::thread::id owner{};
};
World& world() { static World* w = new World; return *w; }
// The TLS depth is in THIS shared library, not separately in each client DSO.
// Thread nesting is registered as ONE outer writer for the entire access span.
thread_local std::array<uint32_t, FABLE_M71_KIND_COUNT> kinds{};
thread_local uint64_t depth = 0;
} // namespace

extern "C" FABLE_M71_EXPORT int fable_memgate71_enter(uint32_t kind) noexcept {
  if (kind >= FABLE_M71_KIND_COUNT || depth == UINT64_MAX || kinds[kind] == UINT32_MAX) return 0;
  auto& w = world();
  std::unique_lock<std::mutex> lock(w.mutex);
  if (depth == 0) {
    // The exclusive owner must not recursively try to enter its own gate.
    // Return failure rather than deadlocking the diagnostic thread.
    if (w.exclusive && w.owner == std::this_thread::get_id()) return 0;
    if (w.requested) {
      ++w.waiting_entries;
      w.cv.wait(lock, [&] { return !w.requested; });
      --w.waiting_entries;
    }
    ++w.active_outer;
  }
  ++depth;
  ++kinds[kind];
  ++w.entries[kind];
  return 1;
}
extern "C" FABLE_M71_EXPORT int fable_memgate71_leave(uint32_t kind) noexcept {
  if (kind >= FABLE_M71_KIND_COUNT || depth == 0 || kinds[kind] == 0) return 0;
  auto& w = world();
  std::unique_lock<std::mutex> lock(w.mutex);
  --depth;
  --kinds[kind];
  if (depth == 0) {
    --w.active_outer;
    lock.unlock();
    w.cv.notify_all();
  }
  return 1;
}
extern "C" FABLE_M71_EXPORT int fable_memgate71_acquire_diagnostic(uint32_t timeout_ms) noexcept {
  // A guest thread cannot pause itself while it holds a writer lease.
  if (depth != 0) return 0;
  auto& w = world();
  std::unique_lock<std::mutex> lock(w.mutex);
  if (w.requested) return 0;
  w.requested = true;  // Blocks NEW outer writers immediately.
  const bool drained = w.cv.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                                     [&] { return w.active_outer == 0; });
  if (!drained) {
    w.requested = false;
    lock.unlock();
    w.cv.notify_all();
    return 0;
  }
  w.exclusive = true;
  w.owner = std::this_thread::get_id();
  ++w.drains;
  return 1;
}
extern "C" FABLE_M71_EXPORT int fable_memgate71_release_diagnostic() noexcept {
  auto& w = world();
  std::unique_lock<std::mutex> lock(w.mutex);
  if (!w.exclusive || w.owner != std::this_thread::get_id()) return 0;
  w.exclusive = false;
  w.requested = false;
  w.owner = std::thread::id{};
  lock.unlock();
  w.cv.notify_all();
  return 1;
}
extern "C" FABLE_M71_EXPORT int fable_memgate71_snapshot(FableMemgate71Snapshot* out,
                                                          uint32_t size) noexcept {
  if (!out || size != sizeof(FableMemgate71Snapshot)) return 0;
  auto& w = world();
  std::lock_guard<std::mutex> lock(w.mutex);
  FableMemgate71Snapshot result{};
  result.abi_version = FABLE_M71_ABI_VERSION;
  result.struct_size = sizeof(result);
  for (unsigned i = 0; i < FABLE_M71_KIND_COUNT; ++i) result.entries[i] = w.entries[i];
  result.active_outer_writers = w.active_outer;
  result.exclusive_diagnostic_acquires = w.drains;
  result.blocked_entries = w.waiting_entries;
  result.diagnostic_exclusive_active = w.exclusive ? 1 : 0;
  result.all_writers_certified = 0;  // Not all DMA/mapping/GPU paths participate.
  result.memexport_commit_permitted = 0;  // Hard safety gate, NEVER lift here.
  *out = result;
  return 1;
}
extern "C" FABLE_M71_EXPORT int fable_memgate71_commit_permitted() noexcept {
  return 0;
}
