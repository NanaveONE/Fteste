#include "fable_memgate71.h"
// Plume exposes explicit entry/exit hooks for future known producer lifetime
// integration. No renderer work is automatically certified or paused yet.
// These exports deliberately do not enable MemExport physical RAM writes.
extern "C" FABLE_M71_EXPORT int fable2_plume71_enter_producer() noexcept {
  return fable_memgate71_enter(FABLE_M71_GPU_PRODUCER);
}
extern "C" FABLE_M71_EXPORT int fable2_plume71_leave_producer() noexcept {
  return fable_memgate71_leave(FABLE_M71_GPU_PRODUCER);
}
extern "C" FABLE_M71_EXPORT int fable2_plume71_commit_allowed() noexcept {
  return fable_memgate71_commit_permitted();
}
