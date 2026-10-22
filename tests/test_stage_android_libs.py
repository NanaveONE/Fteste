import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.check_native_libs import REQUIRED
from scripts.stage_android_libs import collect, stage


class AndroidLibraryStageTests(unittest.TestCase):
    def seed(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        inputs = []
        for name in REQUIRED:
            p = folder / name
            p.write_bytes(b'valid-android-library' * 20)
            inputs.append(p)
        return inputs

    @staticmethod
    def readelf(_, flag, path):
        if flag == '-h':
            return 'Machine: AArch64'
        if flag == '-d':
            if path.name == 'libfable2.so':
                return '(NEEDED) Shared library: [librexruntime.so]\n' \
                       '(NEEDED) Shared library: [libc++_shared.so]'
            if path.name == 'librexgpu-plume.so':
                return '(NEEDED) Shared library: [librexruntime.so]\n' \
                       '(NEEDED) Shared library: [libandroid.so]'
            return ''
        if flag == '--dyn-syms':
            if path.name == 'libfable2.so':
                return 'SDL_main'
            if path.name == 'librexgpu-plume.so':
                return 'rex_gpu_create rex_gpu_abi_version'
            return ''
        raise AssertionError(flag)

    def test_stages_only_reachable_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            unused = root / 'search'; unused.mkdir()
            (unused / 'libunused.so').write_bytes(b'C' * 400)
            out = root / 'staged'
            with patch('scripts.stage_android_libs.run_readelf', side_effect=self.readelf), \
                 patch('scripts.check_native_libs.run_readelf', side_effect=self.readelf):
                files = stage(inputs, [], [unused], out, 'readelf')
            self.assertEqual(len(files), len(REQUIRED))
            self.assertTrue((out / 'libfable2.so').exists())
            self.assertFalse((out / 'libunused.so').exists())

    def test_missing_needed_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            def readelf(_, flag, path):
                if flag == '-d' and path.name == 'libfable2.so':
                    return '(NEEDED) Shared library: [libnotprovided.so]'
                return self.readelf(_, flag, path)
            with patch('scripts.stage_android_libs.run_readelf', side_effect=readelf):
                with self.assertRaisesRegex(ValueError, 'libnotprovided.so'):
                    collect(inputs, [], [], 'readelf')

    def test_burnout_dep_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.seed(Path(tmp) / 'native')
            def readelf(_, flag, path):
                if flag == '-d' and path.name == 'libfable2.so':
                    return '(NEEDED) Shared library: [libmain_eu.so]'
                return self.readelf(_, flag, path)
            with patch('scripts.stage_android_libs.run_readelf', side_effect=readelf):
                with self.assertRaisesRegex(ValueError, 'Burnout'):
                    collect(inputs, [], [], 'readelf')

    def test_duplicate_lib_name_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            alt = root / 'another'; alt.mkdir()
            (alt / 'libfable2.so').write_bytes(b'UNRELATED'*80)
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                collect(inputs, [], [alt], 'readelf')

    def test_wrong_cpu_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            def readelf(_, flag, path):
                if flag == '-h' and path.name == 'libfable2.so':
                    return 'Machine: Advanced Micro Devices X86-64'
                return self.readelf(_, flag, path)
            with patch('scripts.stage_android_libs.run_readelf', side_effect=readelf):
                with self.assertRaisesRegex(ValueError, 'AArch64'):
                    collect(inputs, [], [], 'readelf')

    def test_stage_keeps_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            out = root / 'staged'; out.mkdir()
            (out / 'keep.txt').write_text('untouched')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                stage(inputs, [], [], out, 'readelf')
            self.assertEqual((out / 'keep.txt').read_text(), 'untouched')

    def test_extra_dependency_in_search_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self.seed(root / 'native')
            more = root / 'extra'; more.mkdir()
            (more / 'libSDL3.so').write_bytes(b'J'*500)
            def readelf(_, flag, path):
                if flag == '-d' and path.name == 'librexruntime.so':
                    return '(NEEDED) Shared library: [libSDL3.so]'
                return self.readelf(_, flag, path)
            with patch('scripts.stage_android_libs.run_readelf', side_effect=readelf):
                files = collect(inputs, [], [more], 'readelf')
            self.assertIn('libSDL3.so', files)


if __name__ == '__main__':
    unittest.main()
