"""Tests for Android NDK std::jthread/stop_token port (no game assets)."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.patch_android_timer_thread import ANCHORS, MARKER, patch_clone, patch_source, check_source

ROOT = Path(__file__).resolve().parents[1]


def original_fixture() -> str:
    # Keep the actual upstream anchor text, but build a small self-contained
    # timer to check both compiled paths and prompt join on shutdown.
    return r'''#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <chrono>
#include <memory>
using TimerClock = std::chrono::steady_clock;
struct WaitItem {
  WaitItem(void*,void*,void*,TimerClock::time_point,TimerClock::duration){}
  void Disarm(){}
};
class TimerQueue {
 public:
  TimerQueue() {
    dispatch_thread_ =
        std::jthread([this](std::stop_token stop_token) { TimerThreadMain(stop_token); });
  }
  ~TimerQueue() {
    dispatch_thread_.request_stop();
    auto wait_item = std::make_shared<WaitItem>(nullptr, nullptr, this, TimerClock::time_point::min(),
                                                TimerClock::duration::zero());
    wait_item->Disarm();
    QueueTimer(std::move(wait_item));
    // std::jthread auto-joins on destruction
  }
  void TimerThreadMain(std::stop_token stop_token) {
    while (!stop_token.stop_requested()) {
      std::unique_lock<std::mutex> lock(mutex_);
      cv_.wait_for(lock, std::chrono::milliseconds(5000));
    }
  }
  void QueueTimer(std::shared_ptr<WaitItem>) {
    std::lock_guard<std::mutex> lock(mutex_);
    cv_.notify_all();
  }
  std::jthread::id dispatch_thread_id() const { return dispatch_thread_.get_id(); }
 private:
  std::mutex mutex_;
  std::condition_variable cv_;
  std::jthread dispatch_thread_;
};
int main() {
  for (int i=0; i<80; ++i) { TimerQueue t; }
  return 0;
}
'''


class AndroidTimerPortTests(unittest.TestCase):
    def test_replaces_all_upstream_anchors_and_checks_port(self):
        patched = patch_source(original_fixture())
        self.assertIn(MARKER, patched)
        self.assertIn('stop_requested_.store(true, std::memory_order_release)', patched)
        self.assertIn('dispatch_thread_.join()', patched)
        check_source(patched)
        with self.assertRaisesRegex(ValueError, 'already patched'):
            patch_source(patched)

    def test_fail_closed_when_upstream_layout_changes(self):
        source = original_fixture().replace('dispatch_thread_.request_stop();', 'dispatch_thread_.stop();')
        with self.assertRaisesRegex(ValueError, 'destructor-stop'):
            patch_source(source)

    def test_check_rejects_unpatched_source(self):
        with self.assertRaisesRegex(ValueError, 'marker'):
            check_source(original_fixture())

    def test_clone_only_under_ignored_build_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'build/deps/rexglue-xerenge/src/core/timer_queue.cpp'
            target.parent.mkdir(parents=True)
            target.write_text(original_fixture())
            report = patch_clone(root, target.parents[2])
            self.assertIn('patched', report)
            self.assertIn('already present', patch_clone(root, target.parents[2]))
            self.assertIn('checked', patch_clone(root, target.parents[2], check=True))
            with self.assertRaisesRegex(ValueError, 'disposable clone'):
                patch_clone(root, root / 'external/rexglue-xerenge')

    def test_actual_cpp_android_and_host_thread_shutdown(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler not installed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'timer.cpp'
            path.write_text(patch_source(original_fixture()))
            executable = root / 'timer-test'
            for defines in ([], ['-D__ANDROID__=1']):
                cmd = [compiler, '-std=c++23', '-pthread', '-O0', *defines,
                       str(path), '-o', str(executable)]
                built = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr)
                outcome = subprocess.run([str(executable)], capture_output=True,
                                         text=True, timeout=8)
                self.assertEqual(outcome.returncode, 0, outcome.stderr)

    def test_build_script_applies_patch_before_cmake(self):
        script = (ROOT / 'scripts/build_rexglue_android_sdk.sh').read_text()
        self.assertIn('patch_android_float_from_chars.py', script)
        self.assertIn('patch_android_timer_thread.py', script)
        self.assertLess(script.index('patch_android_float_from_chars.py'),
                        script.index('patch_android_timer_thread.py'))
        self.assertLess(script.index('patch_android_timer_thread.py'),
                        script.index('cmake -S'))
        self.assertIn('patch_android_timer_thread.py" --sdk "$sdk" --root "$root" --check', script)

    def test_android_thread_exit_does_not_leak(self):
        p = patch_source(original_fixture())
        self.assertEqual(p.count('stop_requested_.load(std::memory_order_acquire)'), 1)
        self.assertEqual(p.count('stop_requested_.store(true, std::memory_order_release)'), 1)
        self.assertEqual(p.count('dispatch_thread_.joinable()'), 1)
        self.assertEqual(p.count('dispatch_thread_.join()'), 1)
        self.assertEqual(p.count('std::jthread auto-joins on destruction'), 1)


if __name__ == '__main__':
    unittest.main()
