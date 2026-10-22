"""Tests must never require proprietary game files or build an APK."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.playable_preflight import audit

ROOT = Path(__file__).resolve().parents[1]


class RealBuildGateTests(unittest.TestCase):
    @staticmethod
    def fixture(root: Path, *, valid_xex: bool = True):
        game = root / 'private-game'
        ndk = root / 'ndk'
        sdk = root / 'sdk'
        android_home = root / 'android'
        plume = root / 'plume'
        xenos = root / 'xenos'
        paths = [
            root / 'external/Fable-2-Recomp/CMakeLists.txt',
            root / 'external/Fable-2-Recomp/fable_2_manifest.toml',
            root / 'external/Xerenge/rexglue/src/plume_renderer/plugin_main.cpp',
            game / 'default.xex',
            ndk / 'build/cmake/android.toolchain.cmake',
            ndk / 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so',
            ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf',
            sdk / 'src/core/main_android.cpp',
            sdk / 'src/ui/windowed_app_main_sdl.cpp',
            sdk / 'include/rex/system/gpu_plugin.h',
            root / 'codegen',
            plume / 'CMakeLists.txt',
            xenos / 'XenosRecomp/shader_common.h',
            root / 'translator',
            root / 'dumper',
        ]
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'data')
        (game / 'default.xex').write_bytes(b'XEX2' if valid_xex else b'FAKE')
        (game / 'data/gold_version.txt').parent.mkdir(exist_ok=True)
        (game / 'data/gold_version.txt').write_bytes(b'fixture')
        (game / 'data/startup.vfsconfig').write_bytes(b'fixture')
        catalog = root / 'external/Fable-2-Recomp/constants/game_versions.json'
        catalog.parent.mkdir(exist_ok=True)
        catalog.write_text(json.dumps({'versions': [{
            'id': 'fixture-goty',
            'xexSize': 4,
            'hash': hashlib.sha256(b'XEX2').hexdigest(),
            'compatible': True,
            'requiredFiles': ['data/gold_version.txt', 'data/startup.vfsconfig'],
            'rejectFiles': ['data/tu1_data.bnk'],
        }]}), encoding='utf-8')
        (game / 'data').mkdir(exist_ok=True)
        (android_home / 'build-tools').mkdir(parents=True)
        (android_home / 'platforms').mkdir()
        (sdk / 'thirdparty/sdl3/android-project/app/src/main/java').mkdir(parents=True)
        for exe in (root / 'codegen', root / 'translator', root / 'dumper', paths[6]):
            exe.chmod(exe.stat().st_mode | 0o111)
        return {
            'FABLE2_GAME_ROOT': str(game),
            'ANDROID_NDK_HOME': str(ndk),
            'ANDROID_HOME': str(android_home),
            'REXSDK_DIR': str(sdk),
            'PLUME_ROOT': str(plume),
            'XENOS_RECOMP_ROOT': str(xenos),
            'FABLE2_CODEGEN_TOOL': str(root / 'codegen'),
            'FABLE2_SHADER_TRANSLATOR': str(root / 'translator'),
            'FABLE2_XEX_DUMPER': str(root / 'dumper'),
        }

    def test_rejects_missing_private_game_and_toolchain(self):
        with tempfile.TemporaryDirectory() as folder:
            report = audit(Path(folder), {}, check_host=False)
        self.assertEqual(report['state'], 'BLOCKED')
        names = {item['requirement'] for item in report['failures']}
        self.assertIn('private game default.xex', names)
        self.assertIn('NDK toolchain', names)
        self.assertIn('host ReXGlue code generator', names)

    def test_ready_means_only_prerequisites_present(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root)
            report = audit(root, env, check_host=False)
        self.assertEqual(report['state'], 'PREREQUISITES_PRESENT')
        self.assertFalse(report['failures'])
        self.assertEqual(report['verified_game_profile'], 'fixture-goty')
        self.assertIn('unverified', ''.join(report['warnings']))

    def test_rejects_known_but_unsupported_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root)
            catalog = root / 'external/Fable-2-Recomp/constants/game_versions.json'
            d = json.loads(catalog.read_text())
            d['versions'][0]['compatible'] = False
            catalog.write_text(json.dumps(d))
            report = audit(root, env, check_host=False)
        self.assertIn('catalog profile is explicitly unsupported', [x['reason'] for x in report['failures']])

    def test_rejects_missing_required_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root)
            (Path(env['FABLE2_GAME_ROOT']) / 'data/gold_version.txt').unlink()
            report = audit(root, env, check_host=False)
        self.assertIn('missing data/gold_version.txt', [x['reason'] for x in report['failures']])

    def test_rejects_mixed_tu1_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root)
            (Path(env['FABLE2_GAME_ROOT']) / 'data/tu1_data.bnk').write_bytes(b'x')
            report = audit(root, env, check_host=False)
        self.assertIn('unexpected data/tu1_data.bnk', [x['reason'] for x in report['failures']])

    def test_rejects_renamed_fake_xex(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root, valid_xex=False)
            report = audit(root, env, check_host=False)
        self.assertEqual(report['state'], 'BLOCKED')
        self.assertIn('not an XEX2 executable', [x['reason'] for x in report['failures']])

    def test_report_excludes_private_file_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = self.fixture(root)
            (root / 'translator').unlink()
            report = audit(root, env, check_host=False)
            text = json.dumps(report)
            self.assertNotIn(str(root / 'private-game'), text)
            self.assertNotIn(str(root / 'translator'), text)

    def test_build_command_checks_prerequisites_and_does_not_fake_apk(self):
        run = subprocess.run(
            ['bash', str(ROOT / 'scripts/attempt_playable_build.sh'), '--build'],
            cwd=ROOT,
            env={**os.environ, 'FABLE2_GAME_ROOT': ''},
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertIn('BLOCKED:', run.stdout)
        self.assertFalse((ROOT / 'build/fable2-apk/fable2-arm64.apk').exists())

    def test_native_host_build_uses_real_cmake_target(self):
        source = (ROOT / 'scripts/build_host_tools.sh').read_text()
        self.assertIn('--target xerenge_tool_dump_xex', source)
        self.assertIn('--target rexglue', source)
        self.assertIn('--target XenosRecomp', source)
        self.assertNotIn('--target dump_xex_image ', source)

    def test_device_smoke_never_claims_playable(self):
        text = (ROOT / 'scripts/device_smoke_test.sh').read_text()
        self.assertIn('logcat', text)
        self.assertIn('NOT proof of gameplay', text)
        self.assertNotIn('adb shell rm -rf', text)


if __name__ == '__main__':
    unittest.main()
