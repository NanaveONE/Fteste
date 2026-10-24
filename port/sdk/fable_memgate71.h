#pragma once
// MemExport71: one process-wide cooperative diagnostic gate, via ONE shared
// library. NOT a complete guest stop-the-world implementation or a GPU commit
// permit. Runtime/DMA/mapping paths not yet verified must stay blocked.
#include <stdint.h>
#ifdef __cplusplus
#include <exception>
#endif

#if defined(_WIN32)
#  define FABLE_M71_EXPORT __declspec(dllexport)
#else
#  define FABLE_M71_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#define FABLE_M71_NOEXCEPT noexcept
#else
#define FABLE_M71_NOEXCEPT
#endif

enum {
  FABLE_M71_GUEST_THREAD = 0,
  FABLE_M71_GUEST_CALL = 1,
  FABLE_M71_RUNTIME_HELPER = 2,
  FABLE_M71_GPU_PRODUCER = 3,
  FABLE_M71_DMA_MAPPING = 4,
  FABLE_M71_KIND_COUNT = 5,
  FABLE_M71_ABI_VERSION = 1,
};

typedef struct FableMemgate71Snapshot {
  uint32_t abi_version;
  uint32_t struct_size;
  uint64_t entries[FABLE_M71_KIND_COUNT];
  uint64_t active_outer_writers;
  uint64_t exclusive_diagnostic_acquires;
  uint64_t blocked_entries;
  uint32_t diagnostic_exclusive_active;
  uint32_t all_writers_certified;
  uint32_t memexport_commit_permitted;
  uint32_t reserved;
} FableMemgate71Snapshot;

// Successful enter MUST be paired with a leave on the same thread.
// Nested enters are supported and do not deadlock a pending exclusive request.
FABLE_M71_EXPORT int fable_memgate71_enter(uint32_t kind) FABLE_M71_NOEXCEPT;
FABLE_M71_EXPORT int fable_memgate71_leave(uint32_t kind) FABLE_M71_NOEXCEPT;
// Diagnostic-only drain: never makes GPU writes permissible. Owner must release.
FABLE_M71_EXPORT int fable_memgate71_acquire_diagnostic(uint32_t timeout_ms) FABLE_M71_NOEXCEPT;
FABLE_M71_EXPORT int fable_memgate71_release_diagnostic(void) FABLE_M71_NOEXCEPT;
FABLE_M71_EXPORT int fable_memgate71_snapshot(FableMemgate71Snapshot* output,
                                             uint32_t size) FABLE_M71_NOEXCEPT;
FABLE_M71_EXPORT int fable_memgate71_commit_permitted(void) FABLE_M71_NOEXCEPT;

#ifdef __cplusplus
} // extern "C"
namespace fable2::memgate71 {
class WriterScope final {
 public:
  explicit WriterScope(uint32_t kind) noexcept : kind_(kind), entered_(fable_memgate71_enter(kind) == 1) {
    // An unregistered writer may NEVER be allowed to execute unchecked.
    if (!entered_) std::terminate();
  }
  ~WriterScope() noexcept { if (entered_ && fable_memgate71_leave(kind_) != 1) std::terminate(); }
  WriterScope(const WriterScope&) = delete;
  WriterScope& operator=(const WriterScope&) = delete;
 private:
  uint32_t kind_;
  bool entered_;
};
}
#endif
#undef FABLE_M71_NOEXCEPT
