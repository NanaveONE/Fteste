"""Public tests without any copyrighted game/shader binaries."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import struct
from zipfile import ZipFile

from scripts import integrate_fable2_arm64_probe57 as integ


def synthetic_elf(alignment=16384):
    blob=bytearray(1024)
    blob[0:6]=b'\x7fELF\x02\x01'
    struct.pack_into('<HH',blob,16,3,183)
    struct.pack_into('<Q',blob,32,64)  # e_phoff
    struct.pack_into('<HH',blob,54,56,1)  # phentsize, phnum
    struct.pack_into('<I',blob,64,1)  # PT_LOAD
    struct.pack_into('<QQ',blob,72,0,0)  # p_offset, p_vaddr
    struct.pack_into('<Q',blob,64+48,alignment)  # p_align
    return bytes(blob)


def report():
    return {'status':'PRIVATE_ARM64_GPU_PROBE56_ONLY',
            'expected':588,'compiled':583,'missing':5,
            'missing_hashes':sorted(integ.MISSING_HASHES),
            'cache_sha256':'a'*64,'production_approved':False,
            'guest_memexport_execution_proven':False}


class Integration57Tests(unittest.TestCase):
    def test_partial_probe_remains_nonproduction(self):
        integ.validate_probe_report(report())
        for mutation in ('full', 'missing', 'hash', 'production', 'memexport'):
            d = report()
            if mutation == 'full': d['compiled'] = 588
            elif mutation == 'missing': d['missing_hashes'].pop()
            elif mutation == 'hash': d['cache_sha256'] = 'invalid'
            elif mutation == 'production': d['production_approved'] = True
            elif mutation == 'memexport': d['guest_memexport_execution_proven'] = True
            with self.subTest(mutation=mutation), self.assertRaises(integ.IntegrationBlocked):
                integ.validate_probe_report(d)

    def create_zip(self, path, *, extra=None, bad_report=False):
        with ZipFile(path, 'w') as z:
            z.writestr('librexgpu-plume.so', synthetic_elf())
            d = report()
            if bad_report: d['compiled'] = 572
            z.writestr('gpu-probe56-report.json', json.dumps(d))
            if extra:
                z.writestr(extra, 'untrusted')

    def test_extract_good_private_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'probe.zip'; self.create_zip(source)
            data=integ.extract_gpu_probe(source, root/'librexgpu-plume.so')
            self.assertEqual(data['compiled'],583)
            self.assertEqual((root/'librexgpu-plume.so').stat().st_size,1024)

    def test_reject_unsafe_zip_and_wrong_shader_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,extra,bad in [(1,'../private.txt',False),(2,None,True),(3,'libSDL3.so',False)]:
                archive=root/f'probe{i}.zip'
                self.create_zip(archive, extra=extra,bad_report=bad)
                with self.subTest(case=i), self.assertRaises(integ.IntegrationBlocked):
                    integ.extract_gpu_probe(archive,root/'librexgpu-plume.so')

    @staticmethod
    def fake_readelf(_, flag, path):
        if flag == '-h': return 'Machine: AArch64'
        if flag == '-d':
            if path.name in ('libfable2.so','librexgpu-plume.so'):
                return '(NEEDED) Shared library: [librexruntime.so]\n(NEEDED) Shared library: [libc++_shared.so]'
            return ''
        if flag == '--dyn-syms':
            if path.name == 'libfable2.so': return 'SDL_main'
            if path.name == 'librexgpu-plume.so': return 'rex_gpu_abi_version rex_gpu_create'
            return ''
        raise AssertionError(flag)

    def test_private_integration_packaging_and_4k_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=root/'libfable2.so'; original.write_bytes(synthetic_elf())
            runtime=root/'runtime';runtime.mkdir()
            for name in ('librexruntime.so', 'libc++_shared.so'):
                (runtime/name).write_bytes(synthetic_elf())
            (runtime/'runtime-build-report.json').write_text(json.dumps({
                'status':'ARM64_ELF_AND_DT_NEEDED_VERIFIED','architecture':'aarch64'}))
            probe=root/'probe.zip';self.create_zip(probe)
            dest=root/'private-integration.zip'
            with patch('scripts.stage_android_libs.run_readelf',side_effect=self.fake_readelf), \
                 patch('scripts.check_native_libs.run_readelf',side_effect=self.fake_readelf):
                manifest=integ.integrate(original,probe,runtime,dest,'fake-readelf')
            self.assertFalse(manifest['production_approved'])
            self.assertFalse(manifest['apk_generated'])
            self.assertFalse(manifest['sdk_abi_equivalence_proven'])
            self.assertEqual(len(manifest['libraries']),4)
            with ZipFile(dest) as z:
                self.assertIn('lib/arm64-v8a/libfable2.so', z.namelist())
                self.assertIn('lib/arm64-v8a/librexgpu-plume.so', z.namelist())
            (runtime/'libc++_shared.so').write_bytes(synthetic_elf(4096))
            with patch('scripts.stage_android_libs.run_readelf',side_effect=self.fake_readelf), \
                 patch('scripts.check_native_libs.run_readelf',side_effect=self.fake_readelf):
                with self.assertRaisesRegex(integ.IntegrationBlocked,'16 KiB'):
                    integ.integrate(original,probe,runtime,root/'bad.zip','fake-readelf')
            self.assertFalse((root/'bad.zip').exists())

    def test_android_launch_requests_plume(self):
        source=(Path(__file__).resolve().parents[1]/
                'port/android/java/com/nanaveone/fable2/Fable2Activity.java').read_text()
        self.assertIn('"--gpu_plugin=plume"',source)
        self.assertIn('"--game_data_root="',source)
        self.assertNotIn('"rexgpu-plume"',source)  # Loader does dlopen via ReXGlue.

    def test_private_workflow_no_public_game_artifacts(self):
        workflow=(Path(__file__).resolve().parents[1]/
                 '.github/workflows/build-fable2-arm64-integrate57-private.yml').read_text()
        self.assertIn('gh release upload', workflow)
        self.assertIn('FABLE2_PRIVATE_TOKEN',workflow)
        self.assertIn('integrate_fable2_arm64_probe57.py',workflow)
        self.assertNotIn('actions/upload-artifact',workflow)
        self.assertNotIn('package_android_apk.sh',workflow)


if __name__ == '__main__': unittest.main()
