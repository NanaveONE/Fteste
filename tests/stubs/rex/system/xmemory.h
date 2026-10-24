#pragma once
// Unit-test-only stand-in for the pinned ReXGlue xmemory public API.
// NEVER add tests/stubs to Android native include directories.
#include <array>
#include <cstddef>
#include <cstdint>

namespace rex::memory {
enum class PageAccess { kNoAccess, kReadOnly, kReadWrite };
class PhysicalHeap {
 public:
  std::uint32_t allowed_begin = 0;
  std::uint32_t allowed_end_exclusive = 0;
  PageAccess access = PageAccess::kNoAccess;
  PageAccess QueryRangeAccess(std::uint32_t begin, std::uint32_t end) const {
    if (begin < allowed_begin || end >= allowed_end_exclusive) return PageAccess::kNoAccess;
    return access;
  }
};
class Memory {
 public:
  std::array<std::uint8_t, 256> bytes{};
  PhysicalHeap heap;
  PhysicalHeap* GetPhysicalHeap() { return &heap; }
  template <typename T = std::uint8_t*> T TranslatePhysical(std::uint32_t offset) {
    return offset < bytes.size() ? reinterpret_cast<T>(bytes.data() + offset) : nullptr;
  }
};
} // namespace rex::memory
