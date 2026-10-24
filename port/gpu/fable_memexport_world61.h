#pragma once
// Fable II MemExport61: cooperative *participant* gate for the pinned ReXGlue.
// This does NOT instrument any guest code by itself. No real runtime can be
// certified until every guest executor, CPU writer, producer, and mapping
// operation registers with this gate for its full memory-access lifetime.
#include "fable_memexport_rex60.h"

#include <array>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string_view>
#include <utility>

namespace fable2::memexport61 {

enum class WriterClass : std::size_t {
  GuestExecutor = 0,
  KernelAndJit = 1,
  HostProducer = 2,
  MappingOrInvalidator = 3,
  Count = 4,
};

// The pinned SDK must IMPLEMENT this using actual thread-entry and producer
// hooks. Stock ReXGlue does not meet this contract. The answers must remain
// valid while a stop request is active, including during thread creation and
// memory-map changes; a simple count of existing XThread objects is NOT enough.
class CoverageProof {
 public:
  virtual ~CoverageProof() = default;
  virtual bool EveryMemoryWriterIsInstrumented() const noexcept = 0;
  virtual memexport55::WireEncoding CertifiedXenosEncoding() const noexcept = 0;
  virtual void InvalidatePhysicalCaches(std::uint32_t address,
                                        std::size_t length) noexcept = 0;
};

class CooperativeWorld final : public memexport60::CertifiedGuestWorld {
 public:
  class WriterLease final {
   public:
    WriterLease() = default;
    WriterLease(const WriterLease&) = delete;
    WriterLease& operator=(const WriterLease&) = delete;
    WriterLease(WriterLease&& other) noexcept { *this = std::move(other); }
    WriterLease& operator=(WriterLease&& other) noexcept {
      if (this != &other) {
        Reset();
        world_ = std::exchange(other.world_, nullptr);
        kind_ = other.kind_;
      }
      return *this;
    }
    ~WriterLease() { Reset(); }
    explicit operator bool() const noexcept { return world_ != nullptr; }
    void Reset() noexcept {
      if (world_) {
        world_->ExitWriter(kind_);
        world_ = nullptr;
      }
    }
   private:
    friend class CooperativeWorld;
    WriterLease(CooperativeWorld* world, WriterClass kind) : world_(world), kind_(kind) {}
    CooperativeWorld* world_ = nullptr;
    WriterClass kind_ = WriterClass::GuestExecutor;
  };

  explicit CooperativeWorld(CoverageProof* proof,
                            std::chrono::milliseconds timeout = std::chrono::milliseconds(250))
      : proof_(proof), timeout_(timeout) {}
  CooperativeWorld(const CooperativeWorld&) = delete;
  CooperativeWorld& operator=(const CooperativeWorld&) = delete;

  // Must wrap the COMPLETE access interval, not just the first instruction.
  // A newly created writer will block behind a pending exclusive request.
  // Never hold unrelated kernel locks when calling this blocking entry point.
  WriterLease EnterWriter(WriterClass kind) {
    if (kind == WriterClass::Count) return {};
    std::unique_lock<std::mutex> lock(mutex_);
    ready_.wait(lock, [this] { return !request_ || closing_; });
    if (closing_) return {};
    ++active_[static_cast<std::size_t>(kind)];
    return WriterLease(this, kind);
  }

  bool IsVerifiedFor(std::string_view revision) const noexcept override {
    return revision == memexport60::kPinnedRexSdkRevision && proof_ &&
           proof_->EveryMemoryWriterIsInstrumented();
  }

  bool AcquireAllWriters() override {
    if (!IsVerifiedFor(memexport60::kPinnedRexSdkRevision)) return false;
    std::unique_lock<std::mutex> lock(mutex_);
    if (request_ || closing_) return false;
    request_ = true;
    if (!ready_.wait_for(lock, timeout_, [this] {
          return closing_ || TotalActiveLocked() == 0;
        }) || closing_ || !IsVerifiedFor(memexport60::kPinnedRexSdkRevision)) {
      request_ = false;
      lock.unlock();
      ready_.notify_all();
      return false;
    }
    exclusive_ = true;
    return true;
  }

  bool AllWritersQuiescent() const noexcept override {
    std::lock_guard<std::mutex> lock(mutex_);
    return exclusive_ && request_ && !closing_ && TotalActiveLocked() == 0 &&
           IsVerifiedFor(memexport60::kPinnedRexSdkRevision);
  }

  void ReleaseAllWriters() noexcept override {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      exclusive_ = false;
      request_ = false;
    }
    ready_.notify_all();
  }

  void MarkPhysicalDirty(std::uint32_t address, std::size_t length) noexcept override {
    if (AllWritersQuiescent() && proof_) proof_->InvalidatePhysicalCaches(address, length);
  }

  memexport55::WireEncoding VerifiedEncoding() const noexcept override {
    return IsVerifiedFor(memexport60::kPinnedRexSdkRevision)
        ? proof_->CertifiedXenosEncoding() : memexport55::WireEncoding::Unknown;
  }

  // Shutdown is only safe while the object and its proof outlive all leases.
  void Close() noexcept {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      closing_ = true;
    }
    ready_.notify_all();
  }

  bool PauseRequested() const noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    return request_;
  }

 private:
  void ExitWriter(WriterClass kind) noexcept {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      const auto index = static_cast<std::size_t>(kind);
      if (active_[index] > 0) --active_[index];
    }
    ready_.notify_all();
  }
  std::size_t TotalActiveLocked() const noexcept {
    std::size_t sum = 0;
    for (const auto count : active_) sum += count;
    return sum;
  }

  CoverageProof* proof_;  // External runtime owns and outlives this gate.
  const std::chrono::milliseconds timeout_;
  mutable std::mutex mutex_;
  std::condition_variable ready_;
  std::array<std::size_t, static_cast<std::size_t>(WriterClass::Count)> active_{};
  bool request_ = false;
  bool exclusive_ = false;
  bool closing_ = false;
};

}  // namespace fable2::memexport61
