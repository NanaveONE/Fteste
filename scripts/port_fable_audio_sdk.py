#!/usr/bin/env python3
"""Reconcile Fable II's timed silent-audio fallback with Xerenge's Android SDL.

Only touches the SDK clone in ignored build/ (never Xerenge's submodule).
Keeps Xerenge's DiscardPendingFrames and platform-specific SDL changes.
Fail closed when original SDK source anchors move.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil

CPP_FILE = 'src/audio/sdl/sdl_audio_driver.cpp'
HEADER_FILE = 'include/rex/audio/sdl/sdl_audio_driver.h'
FALLBACK_HEADER = 'include/rex/audio/fable_clocked_audio_sink.h'

INIT_ANCHOR = 'bool SDLAudioDriver::Initialize() {\n'
SUBMIT_ANCHOR = 'void SDLAudioDriver::SubmitFrame(uint32_t frame_ptr) {\n'
SHUTDOWN_ANCHOR = 'void SDLAudioDriver::Shutdown() {\n'

INIT_PATCH = '''bool SDLAudioDriver::Initialize() {
#if defined(__ANDROID__)
  if (InitializeDevice()) return true;
  // Clean up an unsuccessful attempt before using clocked silent output.
  Shutdown();
  silent_sink_ = std::make_unique<rex::audio::FableClockedAudioSink>([this] {
    if (semaphore_ && !semaphore_->Release(1, nullptr)) {
      REXAPU_WARN("Fable II silent audio completion permit failed");
    }
  });
  if (!silent_sink_->Start()) {
    silent_sink_.reset();
    REXAPU_ERROR("Fable II silent-audio fallback worker did not start");
    return false;
  }
  REXAPU_WARN("Audio endpoint unavailable; Fable II using clocked silent output");
  return true;
#else
  return InitializeDevice();
#endif
}

bool SDLAudioDriver::InitializeDevice() {
'''
SUBMIT_PATCH = '''void SDLAudioDriver::SubmitFrame(uint32_t frame_ptr) {
#if defined(__ANDROID__)
  if (silent_sink_) {
    if (!silent_sink_->Submit()) {
      REXAPU_WARN("Fable II silent audio completion queue full or stopped");
    }
    return;
  }
#endif
'''
SHUTDOWN_PATCH = '''void SDLAudioDriver::Shutdown() {
#if defined(__ANDROID__)
  // Join before the AudioSystem destroys its semaphore.
  if (silent_sink_) {
    silent_sink_->Stop();
    silent_sink_.reset();
  }
#endif
'''


def replace_once(source: str, needle: str, replacement: str, purpose: str) -> str:
    if source.count(needle) != 1:
        raise ValueError(f'{purpose}: expected one source anchor, found {source.count(needle)}')
    return source.replace(needle, replacement)


def patch_cpp(source: str) -> str:
    if 'FableClockedAudioSink' in source:
        raise ValueError('Audio source already modified')
    result = replace_once(source, INIT_ANCHOR, INIT_PATCH, 'SDL audio init')
    result = replace_once(result, SUBMIT_ANCHOR, SUBMIT_PATCH, 'SDL audio submit')
    result = replace_once(result, SHUTDOWN_ANCHOR, SHUTDOWN_PATCH, 'SDL audio shutdown')
    # Existing Xerenge-specific DiscardPendingFrames must survive.
    if 'void SDLAudioDriver::DiscardPendingFrames()' not in result:
        raise ValueError('Xerenge SDL audio discard implementation missing')
    return result


def patch_header(source: str) -> str:
    result = replace_once(source, '#include <mutex>\n', '#include <mutex>\n#include <memory>\n', 'SDL audio header')
    result = replace_once(result, '#include <rex/audio/audio_driver.h>\n',
                          '#include <rex/audio/audio_driver.h>\n#include <rex/audio/fable_clocked_audio_sink.h>\n', 'fallback header')
    result = replace_once(result, '  bool Initialize();\n',
                          '  bool Initialize();\n', 'initialize declaration')
    result = replace_once(result, ' protected:\n  static void SDLCallback',
                          ' protected:\n  bool InitializeDevice();\n  static void SDLCallback', 'SDL callback declaration')
    result = replace_once(result, '  bool sdl_initialized_ = false;\n',
                          '  bool sdl_initialized_ = false;\n#if defined(__ANDROID__)\n  std::unique_ptr<rex::audio::FableClockedAudioSink> silent_sink_;\n#endif\n',
                          'SDL audio storage')
    return result


def patch_clone(sdk: Path, root: Path) -> list[str]:
    sdk, root = sdk.resolve(), root.resolve()
    # Only modify an ignored build clone, never tracked source or user's SDK.
    if not sdk.is_relative_to(root / 'build'):
        raise ValueError('SDK must be a disposable, ignored clone under <Fteste>/build/')
    port = root / 'port/sdk/fable_clocked_audio_sink.h'
    if not port.is_file():
        raise ValueError('Fable audio fallback header missing from port/sdk')
    originals = {CPP_FILE: patch_cpp, HEADER_FILE: patch_header}
    changed: dict[str, str] = {}
    marker = 'Fable II silent audio completion'
    for relative, transform in originals.items():
        source_file = sdk / relative
        if not source_file.is_file():
            raise ValueError(f'Missing Android SDK audio source: {relative}')
        text = source_file.read_text(encoding='utf-8')
        if marker in text or 'FableClockedAudioSink' in text:
            raise ValueError('Audio source already modified: inspect the SDK clone before rebuilding')
        changed[relative] = transform(text)
    target = sdk / FALLBACK_HEADER
    if target.exists():
        raise ValueError(f'Audio fallback header already exists: {target}')
    for relative, code in changed.items():
        (sdk / relative).write_text(code, encoding='utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(port, target)
    return [*changed, FALLBACK_HEADER]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk', type=Path, required=True)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args()
    try:
        files = patch_clone(args.sdk, args.root)
    except (OSError, ValueError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    print('Reconciled Fable II Android audio SDK sources:', ', '.join(files))
    print('Audio fallback still requires a real native build and on-device validation')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
