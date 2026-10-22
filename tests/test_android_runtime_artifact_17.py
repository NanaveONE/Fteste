"""Native runtime packaging regression tests; synthetic ELF only."""
from pathlib import Path
import os
import stat
import tempfile
import unittest

from scripts.package_rexruntime_arm64 import find_runtime, inspect, prepare


def fake_so(path: Path, arch: int = 183, marker: bytes = b'') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    header[16:18] = (3).to_bytes(2, 'little')
    header[18:20] = arch.to_bytes(2, 'little')
    path.write_bytes(bytes(header) + b'FAKE_LINKER_FIXTURE' + marker)


def readelf_stub(root: Path) -> str:
    stub = root / 'llvm-readelf'
    stub.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
flag,path=sys.argv[1],Path(sys.argv[2])
if flag=='--dyn-syms':
 print('  1: 0 0 FUNC GLOBAL DEFAULT 1 SDL_main' if path.name=='librexruntime.so' else '')
elif flag=='-d':
 print('Dynamic section at offset 0x100')
 print('0x000000000000000e (SONAME) Library soname: ['+path.name+']')
 if path.name=='librexruntime.so':
  for s in ('libSDL3.so','libc++_shared.so','liblog.so'):
   print('0x0000000000000001 (NEEDED) Shared library: ['+s+']')
 elif path.name=='libSDL3.so':
  print('0x0000000000000001 (NEEDED) Shared library: [libc++_shared.so]')
else:
 sys.exit(3)
''', encoding='utf-8')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return str(stub)


class RuntimePackageTests(unittest.TestCase):
    def fixture(self, root):
        sdk = root / 'build/deps/rexglue-xerenge'
        build = root / 'build/rexglue-android-arm64'
        ndk = root / 'ndk'
        build.mkdir(parents=True)
        runtime = sdk / 'out/android-arm64/librexruntime.so'
        fake_so(runtime)
        fake_so(sdk / 'out/android-arm64/libSDL3.so')
        fake_so(ndk / 'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so')
        return sdk, build, ndk, runtime

    def test_runtime_is_under_sdk_out_not_cmake_build(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            self.assertEqual(find_runtime(sdk, build), runtime)
            self.assertEqual(list(build.rglob('librexruntime.so')), [])

    def test_stages_transitive_needed_deps_and_report(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            out = root / 'build/artifacts/rexglue-android-arm64'
            report = prepare(sdk, build, ndk, out, readelf_stub(root))
            self.assertEqual(set(report['libraries']), {'librexruntime.so','libSDL3.so','libc++_shared.so'})
            self.assertTrue(report['exports_sdl_main'])
            self.assertEqual(report['architecture'], 'aarch64')
            for name in report['libraries']:
                self.assertTrue((out / name).is_file(), name)
            self.assertTrue((out / 'runtime-build-report.json').is_file())
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare(sdk, build, ndk, out, readelf_stub(root))

    def test_missing_dependency_does_not_publish_partial(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            (sdk / 'out/android-arm64/libSDL3.so').unlink()
            out = root / 'build/artifacts/rexglue-android-arm64'
            with self.assertRaisesRegex(ValueError, 'Unresolved ARM64 runtime DT_NEEDED: libSDL3.so'):
                prepare(sdk, build, ndk, out, readelf_stub(root))
            self.assertFalse(out.exists())

    def test_reject_wrong_elf_arch_even_if_soname_matches(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            fake_so(runtime, arch=62)
            with self.assertRaisesRegex(ValueError, 'Not an AArch64'):
                prepare(sdk, build, ndk, root / 'out', readelf_stub(root))

    def test_conflicting_duplicate_outputs_fail(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            fake_so(build / 'src/system/librexruntime.so', marker=b'different')
            with self.assertRaisesRegex(ValueError, 'stale build collision'):
                find_runtime(sdk, build)

    def test_support_build_dir_fallback(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sdk, build, ndk, runtime = self.fixture(root)
            runtime.unlink()
            second = build / 'src/system/librexruntime.so'
            fake_so(second)
            self.assertEqual(find_runtime(sdk, build), second)

    def test_workflow_uses_staged_artifact(self):
        source = Path(__file__).resolve().parents[1]
        script = (source / 'scripts/build_rexglue_android_sdk.sh').read_text()
        wf = (source / '.github/workflows/build-android-runtime.yml').read_text()
        self.assertIn('package_rexruntime_arm64.py', script)
        self.assertNotIn('find "$build" -type f -name librexruntime.so', script)
        self.assertIn('build/artifacts/rexglue-android-arm64/', wf)
        self.assertNotIn('build/rexglue-android-arm64/**/librexruntime.so', wf)


if __name__ == '__main__':
    unittest.main()

class ChainIntegrationTests(unittest.TestCase):
    def test_playable_build_reuses_verified_staging(self):
        source = Path(__file__).resolve().parents[1]
        script = (source / 'scripts/attempt_playable_build.sh').read_text()
        self.assertIn('build/artifacts/rexglue-android-arm64/librexruntime.so', script)
        self.assertIn('args+=(--search-dir "$(dirname "$(realpath "$REXRUNTIME_LIB")")")', script)
        self.assertNotIn('find "$root/build/rexglue-android-arm64"', script)
        self.assertIn('--min-coverage 1.0', script)
        self.assertIn('stage_android_libs.py', script)
