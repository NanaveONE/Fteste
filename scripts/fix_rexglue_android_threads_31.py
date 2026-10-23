#!/usr/bin/env python3
"""Adapt pinned ReXGlue timer queue to Android NDK libc++ without std::jthread."""
from pathlib import Path
import argparse
import sys


def patch(path: Path):
    source = path.read_text(encoding='utf-8')
    if 'ANDROID_TIMER_THREAD_COMPAT_31' in source:
        return 'already patched'
    required = [
        'std::jthread([this](std::stop_token stop_token) { TimerThreadMain(stop_token); });',
        'dispatch_thread_.request_stop();',
        'void TimerThreadMain(std::stop_token stop_token)',
        'while (!stop_token.stop_requested())',
        'std::jthread::id dispatch_thread_id() const',
        'std::jthread dispatch_thread_;',
        '// std::jthread auto-joins on destruction',
    ]
    for s in required:
        if source.count(s) != 1:
            raise ValueError(f'Unexpected SDK timer_queue.cpp revision; anchor count != 1: {s}')
    source = source.replace('#include <algorithm>', '#include <algorithm>\n#include <atomic>\n#include <thread>\n// ANDROID_TIMER_THREAD_COMPAT_31')
    source = source.replace('std::jthread([this](std::stop_token stop_token) { TimerThreadMain(stop_token); });', 'std::thread([this] { TimerThreadMain(); });')
    source = source.replace('dispatch_thread_.request_stop();', 'stop_requested_.store(true, std::memory_order_release);')
    source = source.replace('// std::jthread auto-joins on destruction', 'if (dispatch_thread_.joinable()) dispatch_thread_.join();')
    source = source.replace('void TimerThreadMain(std::stop_token stop_token)', 'void TimerThreadMain()')
    source = source.replace('while (!stop_token.stop_requested())', 'while (!stop_requested_.load(std::memory_order_acquire))')
    source = source.replace('std::jthread::id dispatch_thread_id() const', 'std::thread::id dispatch_thread_id() const')
    source = source.replace('std::jthread dispatch_thread_;', 'std::atomic<bool> stop_requested_{false};\n  std::thread dispatch_thread_;')
    path.write_text(source, encoding='utf-8')
    return 'patched'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    path = args.sdk / 'src/core/timer_queue.cpp'
    try:
        print(patch(path))
    except (ValueError, OSError) as e:
        sys.exit(f'BLOCKED: {e}')


if __name__ == '__main__':
    main()
