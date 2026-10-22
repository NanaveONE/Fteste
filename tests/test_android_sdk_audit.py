import tempfile
import unittest
from pathlib import Path
from scripts.audit_android_sdk import REQUIRED_FILES, source_audit


class AuditSdkTests(unittest.TestCase):
    def seed(self, root):
        for rel, anchors in REQUIRED_FILES.items():
            file = root / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('\n'.join(anchors))
        (root / 'src/ui/windowed_app_main_sdl.cpp').write_text(
            'REX_PLATFORM_ANDROID\nextern "C" int SDL_main(int argc, char** argv) { return 0; }')
        (root / 'include/rex/system/gpu_plugin.h').write_text(
            'inline constexpr uint32_t kGpuPluginAbiVersion = 1;\nrex_gpu_create')

    def test_accepts_required_android_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            sdk = Path(temp) / 'sdk'
            self.seed(sdk)
            report = source_audit(sdk)
            self.assertTrue(report['ready_for_source_build'], report)
            self.assertEqual(report['gpu_plugin_abi'], 1)

    def test_rejects_non_android_sdk(self):
        with tempfile.TemporaryDirectory() as temp:
            sdk = Path(temp) / 'sdk'
            self.seed(sdk)
            (sdk / 'src/ui/windowed_app_main_sdl.cpp').write_text('int main(int,char**);')
            report = source_audit(sdk)
            self.assertFalse(report['ready_for_source_build'])
            self.assertTrue(any('SDL_main' in s for s in report['errors']))

    def test_rejects_absent_android_port_files(self):
        with tempfile.TemporaryDirectory() as temp:
            report = source_audit(Path(temp))
            self.assertFalse(report['ready_for_source_build'])
            self.assertEqual(len(report['missing']), len(REQUIRED_FILES))

    def test_catches_gpu_abi_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sdk = root / 'sdk'
            original = root / 'other'
            self.seed(sdk)
            f = original / 'include/rex/system/gpu_plugin.h'
            f.parent.mkdir(parents=True)
            f.write_text('kGpuPluginAbiVersion = 7')
            report = source_audit(sdk, original)
            self.assertFalse(report['ready_for_source_build'])
            self.assertIn('differ', ' '.join(report['errors']))


if __name__ == '__main__':
    unittest.main()
