import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.port_fable_audio_sdk import patch_cpp, patch_header, patch_clone

ROOT = Path(__file__).resolve().parents[1]


class FableAudioSdkTests(unittest.TestCase):
    CPP = '''bool SDLAudioDriver::Initialize() {
  return true;
}
void SDLAudioDriver::DiscardPendingFrames() {}
void SDLAudioDriver::SubmitFrame(uint32_t frame_ptr) {
  (void)frame_ptr;
}
void SDLAudioDriver::Shutdown() {
}
'''
    HEADER = '''#include <mutex>
#include <rex/audio/audio_driver.h>
class SDLAudioDriver {
  bool Initialize();
 protected:
  static void SDLCallback();
  bool sdl_initialized_ = false;
};
'''

    def test_audio_sources_reconciled_and_not_disable_sdl(self):
        cpp = patch_cpp(self.CPP)
        self.assertIn('if (InitializeDevice()) return true;', cpp)
        self.assertIn('ClockedAudioSink', cpp)
        self.assertIn('void SDLAudioDriver::DiscardPendingFrames()', cpp)
        self.assertIn('return InitializeDevice();', cpp)
        header = patch_header(self.HEADER)
        self.assertIn('fable_clocked_audio_sink.h', header)
        self.assertIn('std::unique_ptr', header)
        with self.assertRaisesRegex(ValueError, 'already modified'):
            patch_cpp(cpp)

    def test_edits_only_disposable_sdk_under_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = root / 'build/deps/rexglue-xerenge'
            cpp = sdk / 'src/audio/sdl/sdl_audio_driver.cpp'
            h = sdk / 'include/rex/audio/sdl/sdl_audio_driver.h'
            cpp.parent.mkdir(parents=True)
            h.parent.mkdir(parents=True)
            cpp.write_text(self.CPP)
            h.write_text(self.HEADER)
            port = root / 'port/sdk'
            port.mkdir(parents=True)
            shutil.copy2(ROOT / 'port/sdk/fable_clocked_audio_sink.h', port)
            result = patch_clone(sdk, root)
            self.assertEqual(len(result), 3)
            self.assertTrue((sdk / 'include/rex/audio/fable_clocked_audio_sink.h').exists())
            with self.assertRaisesRegex(ValueError, 'already modified'):
                patch_clone(sdk, root)
            with self.assertRaisesRegex(ValueError, 'disposable'):
                patch_clone(root / 'external/sdk', root)

    def test_silent_sink_thread_completes_frames(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler not installed')
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / 'test.cpp'
            program.write_text('''#include <atomic>
#include <chrono>
#include <thread>
#include "fable_clocked_audio_sink.h"
int main() {
  std::atomic<int> done{0};
  rex::audio::FableClockedAudioSink sink([&] { ++done; });
  if (!sink.Start() || !sink.Submit() || !sink.Submit()) return 2;
  std::this_thread::sleep_for(std::chrono::milliseconds(60));
  sink.Stop();
  return done.load() == 2 ? 0 : 1;
}
''')
            executable = Path(tmp) / 'sink'
            comp = subprocess.run([compiler, '-std=c++20', '-pthread', '-O0',
                                   '-I', str(ROOT / 'port/sdk'), str(program), '-o', str(executable)],
                                  text=True, capture_output=True)
            self.assertEqual(comp.returncode, 0, comp.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)

if __name__ == '__main__':
    unittest.main()
