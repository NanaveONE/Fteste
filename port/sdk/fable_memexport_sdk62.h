#pragma once
// MemExport62: observation of real ReXGlue guest execution / memory helpers.
// This is diagnostic instrumentation, NOT a stop-the-world implementation.
// No writer can be certified merely because these counters reach zero.
// Direct recompiled stores, kernel, GPU, audio, DMA, async producers and new
// thread creation are NOT exhaustively covered by these four scopes.
#include <atomic>
#include <cstdint>
#include <limits>

namespace fable2::memexport62 {

enum class WriterPath : unsigned { GuestExecute, MemoryZero, MemoryFill, MemoryCopy };

struct Snapshot {
  std::uint64_t guest_entries;
  std::uint64_t memory_helpers;
  std::uint64_t helper_bytes;
  std::uint64_t active_guest_executors;
  std::uint64_t active_memory_helpers;
  std::uint64_t peak_guest_executors;
  bool globally_exclusive_verified;
};

class RuntimeAudit final {
 public:
  RuntimeAudit() = default;
  RuntimeAudit(const RuntimeAudit&) = delete;
  RuntimeAudit& operator=(const RuntimeAudit&) = delete;

  void Enter(WriterPath path, std::uint32_t bytes) noexcept {
    if (path == WriterPath::GuestExecute) {
      guest_entries_.fetch_add(1, std::memory_order_relaxed);
      const auto active = active_guest_.fetch_add(1, std::memory_order_acq_rel) + 1;
      auto old = peak_guest_.load(std::memory_order_relaxed);
      while (old < active && !peak_guest_.compare_exchange_weak(
          old, active, std::memory_order_relaxed, std::memory_order_relaxed)) {}
    } else {
      memory_helpers_.fetch_add(1, std::memory_order_relaxed);
      helper_bytes_.fetch_add(bytes, std::memory_order_relaxed);
      active_helpers_.fetch_add(1, std::memory_order_acq_rel);
    }
  }
  void Exit(WriterPath path) noexcept {
    if (path == WriterPath::GuestExecute)
      active_guest_.fetch_sub(1, std::memory_order_acq_rel);
    else
      active_helpers_.fetch_sub(1, std::memory_order_acq_rel);
  }

  Snapshot Read() const noexcept {
    return {guest_entries_.load(std::memory_order_relaxed),
            memory_helpers_.load(std::memory_order_relaxed),
            helper_bytes_.load(std::memory_order_relaxed),
            active_guest_.load(std::memory_order_acquire),
            active_helpers_.load(std::memory_order_acquire),
            peak_guest_.load(std::memory_order_relaxed),
            false}; // NEVER equate observed inactive paths with guest exclusion.
  }
  // The current SDK does not instrument all asynchronous and direct guest
  // writers, so no real MemExport61 CoverageProof may return true yet.
  bool EveryMemoryWriterIsInstrumented() const noexcept { return false; }

 private:
  std::atomic<std::uint64_t> guest_entries_{0};
  std::atomic<std::uint64_t> memory_helpers_{0};
  std::atomic<std::uint64_t> helper_bytes_{0};
  std::atomic<std::uint64_t> active_guest_{0};
  std::atomic<std::uint64_t> active_helpers_{0};
  std::atomic<std::uint64_t> peak_guest_{0};
};

// Inline function-local static: one tracker for the pinned ReXGlue DSO that
// compiles the instrumented XThread and memory sources. Not linked into Plume.
inline RuntimeAudit& Audit() noexcept {
  static RuntimeAudit tracker;
  return tracker;
}

class WriterScope final {
 public:
  explicit WriterScope(WriterPath path, std::uint32_t bytes = 0) noexcept
      : path_(path) { Audit().Enter(path_, bytes); }
  ~WriterScope() { Audit().Exit(path_); }
  WriterScope(const WriterScope&) = delete;
  WriterScope& operator=(const WriterScope&) = delete;
 private:
  WriterPath path_;
};

} // namespace fable2::memexport62
