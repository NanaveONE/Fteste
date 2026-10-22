// SPDX-License-Identifier: BSD-3-Clause
// Fable II Android: bounded, clocked silent-audio fallback when SDL cannot
// open a device. Inspired by himdo/rexglue-sdk's ClockedAudioSink.
// The game still receives 48 kHz / 256-sample completion permits; real audio
// continues to use SDL3 normally when a device is available.
#pragma once

#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>

namespace rex::audio {
class FableClockedAudioSink {
 public:
  explicit FableClockedAudioSink(std::function<void()> completed)
      : completed_(std::move(completed)) {}
  ~FableClockedAudioSink() { Stop(); }
  FableClockedAudioSink(const FableClockedAudioSink&) = delete;
  FableClockedAudioSink& operator=(const FableClockedAudioSink&) = delete;

  bool Start() {
    std::lock_guard guard(mutex_);
    if (running_) return false;
    running_ = true;
    try {
      thread_ = std::thread([this] { Run(); });
    } catch (...) {
      running_ = false;
      return false;
    }
    return true;
  }

  bool Submit() {
    std::lock_guard guard(mutex_);
    if (!running_ || queued_ >= 64) return false;
    ++queued_;
    wake_.notify_one();
    return true;
  }

  void Stop() {
    {
      std::lock_guard guard(mutex_);
      running_ = false;
      wake_.notify_all();
    }
    if (thread_.joinable()) thread_.join();
    std::lock_guard guard(mutex_);
    queued_ = 0;
  }

 private:
  void Run() {
    using Clock = std::chrono::steady_clock;
    const auto period = std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double>(256.0 / 48000.0));
    auto next = Clock::now() + period;
    std::unique_lock lock(mutex_);
    while (running_) {
      if (!queued_) {
        wake_.wait(lock, [this] { return !running_ || queued_ != 0; });
        next = Clock::now() + period;
      }
      if (!running_) break;
      if (wake_.wait_until(lock, next, [this] { return !running_; })) break;
      --queued_;
      lock.unlock();
      completed_();
      lock.lock();
      next += period;
      if (next < Clock::now()) next = Clock::now() + period;
    }
  }

  std::function<void()> completed_;
  std::mutex mutex_;
  std::condition_variable wake_;
  std::thread thread_;
  bool running_ = false;
  unsigned queued_ = 0;
};
}  // namespace rex::audio
