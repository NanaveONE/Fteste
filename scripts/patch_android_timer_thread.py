#!/usr/bin/env python3
"""Port ReXGlue timer_queue.cpp's jthread/stop_token to Android NDK r27.

This overlay only touches a disposable SDK clone under <Fteste>/build/.
For non-Android builds the upstream std::jthread implementation is preserved.
Do not substitute std::thread without an explicit stop and join: callbacks
may otherwise execute after TimerQueue/WaitItem state has been freed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

TARGET = Path('src/core/timer_queue.cpp')
MARKER = '// FABLE2_ANDROID_TIMER_THREAD_PORT_16'

ANCHORS = {
    'includes': ('#include <condition_variable>\n#include <mutex>\n',
                 '#include <condition_variable>\n#include <mutex>\n'
                 '#if defined(__ANDROID__)\n'
                 '#include <atomic>\n#include <thread>\n'
                 '#endif\n' + MARKER + '\n'),
    'constructor': (
        '    dispatch_thread_ =\n'
        '        std::jthread([this](std::stop_token stop_token) { TimerThreadMain(stop_token); });',
        '#if defined(__ANDROID__)\n'
        '    dispatch_thread_ = std::thread([this] { TimerThreadMain(); });\n'
        '#else\n'
        '    dispatch_thread_ =\n'
        '        std::jthread([this](std::stop_token stop_token) { TimerThreadMain(stop_token); });\n'
        '#endif'),
    'destructor-stop': (
        '    dispatch_thread_.request_stop();',
        '#if defined(__ANDROID__)\n'
        '    stop_requested_.store(true, std::memory_order_release);\n'
        '#else\n'
        '    dispatch_thread_.request_stop();\n'
        '#endif'),
    'destructor-join': (
        '    // std::jthread auto-joins on destruction',
        '#if defined(__ANDROID__)\n'
        '    // Finish all callbacks before the TimerQueue/WaitItem memory is freed.\n'
        '    if (dispatch_thread_.joinable()) dispatch_thread_.join();\n'
        '#else\n'
        '    // std::jthread auto-joins on destruction\n'
        '#endif'),
    'worker-signature': (
        '  void TimerThreadMain(std::stop_token stop_token) {',
        '#if defined(__ANDROID__)\n'
        '  void TimerThreadMain() {\n'
        '#else\n'
        '  void TimerThreadMain(std::stop_token stop_token) {\n'
        '#endif'),
    'worker-loop': (
        '    while (!stop_token.stop_requested()) {',
        '#if defined(__ANDROID__)\n'
        '    while (!stop_requested_.load(std::memory_order_acquire)) {\n'
        '#else\n'
        '    while (!stop_token.stop_requested()) {\n'
        '#endif'),
    'thread-id': (
        '  std::jthread::id dispatch_thread_id() const { return dispatch_thread_.get_id(); }',
        '  std::thread::id dispatch_thread_id() const { return dispatch_thread_.get_id(); }'),
    'member': (
        '  std::jthread dispatch_thread_;',
        '#if defined(__ANDROID__)\n'
        '  std::atomic<bool> stop_requested_{false};\n'
        '  std::thread dispatch_thread_;\n'
        '#else\n'
        '  std::jthread dispatch_thread_;\n'
        '#endif'),
}


def patch_source(source: str) -> str:
    if MARKER in source:
        raise ValueError('Timer source is already patched: use --check, not a second patch')
    result = source
    for name, (old, new) in ANCHORS.items():
        hits = result.count(old)
        if hits != 1:
            raise ValueError(f'Timer source changed ({name}): expected one anchor, found {hits}')
        result = result.replace(old, new, 1)
    return result


def check_source(source: str) -> None:
    if source.count(MARKER) != 1:
        raise ValueError('Missing or duplicate Fable II Android timer patch marker')
    for name, (_old, new) in ANCHORS.items():
        if source.count(new) != 1:
            raise ValueError(f'Timer patch incomplete or duplicated: {name}')
    if '    dispatch_thread_.join();' not in source and '    if (dispatch_thread_.joinable()) dispatch_thread_.join();' not in source:
        raise ValueError('Android timer dispatch thread is not joined')
    if 'stop_requested_.store(true, std::memory_order_release)' not in source:
        raise ValueError('Android timer dispatch thread is not asked to stop')


def patch_clone(root: Path, sdk: Path, *, check: bool = False) -> str:
    root, sdk = root.resolve(), sdk.resolve()
    if not sdk.is_relative_to(root / 'build'):
        raise ValueError('SDK must be a disposable clone under Fteste/build/, not an upstream submodule')
    target = sdk / TARGET
    if not target.is_file():
        raise ValueError(f'ReXGlue timer source missing: {target}')
    source = target.read_text(encoding='utf-8')
    if check:
        check_source(source)
        return 'OK: checked Android thread shutdown/stop/join'
    if MARKER in source:
        check_source(source)
        return 'OK: Android timer patch already present'
    rewritten = patch_source(source)
    check_source(rewritten)
    target.write_text(rewritten, encoding='utf-8')
    return 'OK: patched Android timer queue; Linux jthread code preserved'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(patch_clone(args.root, args.sdk, check=args.check))
    except (OSError, ValueError) as error:
        parser.exit(2, f'BLOCKED: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
