import tempfile
import unittest
from pathlib import Path
from scripts.prepare_android_target import (
    ORIGINAL, REPLACEMENT, GPU_ORIGINAL, GPU_REPLACEMENT,
    GPU_CONFIG_OLD, PATH_START_OLD, PATH_STORAGE_OLD,
    CONFIG_LOAD_OLD, PATH_CONFIG_ORIGINAL, DESKTOP_STAGING_START, DESKTOP_STAGING_END,
    DESKTOP_ARTWORK_START, DESKTOP_ARTWORK_END,
    replace_target, patch_app, patch_main, prepare, excluded,
)


class PortOverlayTests(unittest.TestCase):
    def test_patches_native_library_and_gpu_plugin(self):
        content = ORIGINAL + "\n" + GPU_ORIGINAL
        result = replace_target(content)
        self.assertIn(REPLACEMENT, result)
        self.assertIn(GPU_REPLACEMENT, result)
        self.assertIn("fable2_touch.cpp", result)
        self.assertIn("rexglue_setup_target(fable_2)", result)
        self.assertIn('NOT TARGET fable_2_recomp', result)
        self.assertIn('generated/default/sources.cmake', result)
        self.assertIn("GPU_PLUGINS xenos", result)

    def test_fails_closed_when_upstream_cmake_changed(self):
        with self.assertRaisesRegex(ValueError, "expected one upstream anchor"):
            replace_target("add_executable(fable_2 main.cpp)")

    def test_gpu_pre_setup_defaults_to_android_plume(self):
        data = "\n".join([GPU_CONFIG_OLD, CONFIG_LOAD_OLD, PATH_CONFIG_ORIGINAL, PATH_STORAGE_OLD])
        patched = patch_app(data)
        self.assertIn('config.gpu_plugin.empty() ? "plume"', patched)
        self.assertIn('config.gpu_plugin.empty() ? "xenos"', patched)
        self.assertIn("FABLE2_GAME_ROOT", patched)
        self.assertIn('fable2::config::Load(settings_dir / "fable2_config.toml");', patched)
        self.assertIn("FABLE2_USER_ROOT", patched)
        self.assertIn('paths.cache_root = writable_root / "cache"', patched)
        self.assertIn('paths.user_data_root = exe_dir / "saves"', patched)

    def test_identical_exe_dir_outside_path_hook_unchanged(self):
        # Actual upstream has the same declaration both in OnPostInitLogging
        # and in OnConfigurePaths. The old global replace made CI fail.
        original = "\n".join([
            '  void OnPostInitLogging() override {', PATH_START_OLD,
            CONFIG_LOAD_OLD, '  }',
            PATH_CONFIG_ORIGINAL, PATH_STORAGE_OLD, '  }', GPU_CONFIG_OLD,
        ])
        updated = patch_app(original)
        self.assertEqual(updated.count('rex::filesystem::GetExecutableFolder();'), 2)
        self.assertEqual(updated.count('if (paths.game_data_root.empty())'), 1)
        self.assertIn('fable2::config::Load(settings_dir / "fable2_config.toml");', updated)
        self.assertIn('fable2::config::Load(exe_dir / "fable2_config.toml");', updated)

    def test_real_upstream_android_overlay(self):
        # On GitHub Actions, this tests the pinned REAL code instead of
        # synthetic strings, preventing repeat of the integration 05-07 CI failure.
        upstream = Path(__file__).resolve().parents[1] / 'external/Fable-2-Recomp'
        if not (upstream / 'CMakeLists.txt').is_file():
            self.skipTest('Submodules unavailable on this host')
        cmake = replace_target((upstream / 'CMakeLists.txt').read_text())
        app = patch_app((upstream / 'src/core/fable_2_app.h').read_text())
        patch_main((upstream / 'src/main.cpp').read_text())
        self.assertIn('add_library(fable_2 SHARED', cmake)
        self.assertIn('if(NOT ANDROID)', cmake)
        self.assertIn('endif() # NOT ANDROID: desktop app icon/command file', cmake)
        self.assertIn('fable2::config::Load(settings_dir / "fable2_config.toml");', app)
        self.assertEqual(app.count('if (paths.game_data_root.empty())'), 2)

    def test_desktop_staging_is_not_copied_into_an_android_library_directory(self):
        original = 'x\n' + DESKTOP_STAGING_START + '\nadd_custom_target(lua)\n' + DESKTOP_STAGING_END
        from scripts.prepare_android_target import patch_desktop_staging
        changed = patch_desktop_staging(original)
        self.assertIn('if(NOT ANDROID)\n' + DESKTOP_STAGING_START, changed)
        self.assertIn('endif() # NOT ANDROID', changed)

    def test_desktop_artwork_staging_excluded_from_android(self):
        from scripts.prepare_android_target import patch_desktop_artwork
        source = DESKTOP_ARTWORK_START + '\n  COMMAND echo test\n)\n' + DESKTOP_ARTWORK_END
        changed = patch_desktop_artwork(source)
        self.assertIn('if(NOT ANDROID)\n' + DESKTOP_ARTWORK_START, changed)
        self.assertIn('endif() # NOT ANDROID: desktop app icon/command file', changed)

    def test_win_only_diagnostics_guarded(self):
        sample = '#include "fable2_av_probe.h"\n#include "fable2_stall_dump.h"\n'
        patched = patch_main(sample)
        self.assertEqual(patched.count("#ifdef _WIN32"), 2)
        self.assertIn('#include "fable2_stall_dump.h"', patched)

    def test_refuses_reapplying_an_android_patch(self):
        sample = patch_app("\n".join([GPU_CONFIG_OLD, CONFIG_LOAD_OLD, PATH_CONFIG_ORIGINAL, PATH_STORAGE_OLD]))
        with self.assertRaisesRegex(ValueError, "expected one upstream anchor"):
            patch_app(sample)

    def test_omits_game_files_and_nested_sdk_copy(self):
        result = excluded(".", [".git", "data", "default.xex", "game.iso", "src", "rexglue-sdk"])
        self.assertEqual(result, {".git", "data", "default.xex", "game.iso", "rexglue-sdk"})

    def test_prepare_never_mutates_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            src = base / "upstream"
            src.mkdir()
            (src / "src/core").mkdir(parents=True)
            (src / "CMakeLists.txt").write_text(ORIGINAL + "\n" + GPU_ORIGINAL)
            (src / "src/core/fable_2_app.h").write_text("\n".join([
                GPU_CONFIG_OLD, CONFIG_LOAD_OLD, PATH_CONFIG_ORIGINAL, PATH_STORAGE_OLD]))
            (src / "src/main.cpp").write_text('#include "fable2_av_probe.h"\n#include "fable2_stall_dump.h"\n')
            (src / "default.xex").write_bytes(b"NEVER INCLUDE")
            port = base / "port/android/native"
            port.mkdir(parents=True)
            (port / "fable2_touch.cpp").write_text('// native')
            worktree = base / "worktree"
            changed = prepare(src, worktree, base / "port")
            self.assertEqual(len(changed), 3)
            self.assertIn('GPU_PLUGINS xenos', (src / 'CMakeLists.txt').read_text())
            self.assertIn('rexglue_setup_target(fable_2)', (worktree / 'CMakeLists.txt').read_text())
            self.assertFalse((worktree / 'default.xex').exists())
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare(src, worktree, base / 'port')


if __name__ == '__main__':
    unittest.main()
