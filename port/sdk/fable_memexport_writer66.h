#pragma once
// MemExport66: diagnostic observation of actual guest write call lifetimes.
// Neither these atomics nor this wrapper synchronize GPU/CPU memory. They are
// not a stop-the-world lock and MUST NOT authorize MemExport guest RAM writes.
#include <atomic>
#include <cstdint>
#include <utility>

namespace fable2::memexport66 {

enum class Kind : unsigned { Atomic = 0, MemoryIntrinsic = 1 };

struct Counters {
  std::atomic<std::uint64_t> atomic_calls{0};
  std::atomic<std::uint64_t> intrinsic_calls{0};
  std::atomic<std::uint64_t> active_calls{0};
  std::atomic<std::uint64_t> completed_calls{0};
};

// Per linked image (libfable2.so), NOT a cross-library interlock.
inline Counters& GetCounters() noexcept {
  static Counters state;
  return state;
}

template <class Fn>
decltype(auto) ObserveWrite(Kind kind, Fn&& operation)
    noexcept(noexcept(std::forward<Fn>(operation)())) {
  auto& counters = GetCounters();
  if (kind == Kind::Atomic) {
    counters.atomic_calls.fetch_add(1, std::memory_order_relaxed);
  } else {
    counters.intrinsic_calls.fetch_add(1, std::memory_order_relaxed);
  }
  counters.active_calls.fetch_add(1, std::memory_order_relaxed);
  struct Exit final {
    Counters& counters;
    ~Exit() noexcept {
      counters.completed_calls.fetch_add(1, std::memory_order_relaxed);
      counters.active_calls.fetch_sub(1, std::memory_order_relaxed);
    }
  } exit{counters};
  // Evaluate once; arguments and builtin memory ordering remain inside the
  // original expression, after the observer entered its diagnostic interval.
  return std::forward<Fn>(operation)();
}

// Explicit evidence: no certified global writer lock exists in this header.
inline constexpr bool kGuestWorldCertified = false;
inline constexpr bool kMemExportCommitPermitted = false;

}  // namespace fable2::memexport66
