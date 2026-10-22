#!/usr/bin/env python3
"""Apply Android-only portability fixes to a copy of Fable-2-Recomp.

The generated worktree is NOT an Android gameplay build. Real game code and a
Fable-compatible Vulkan GPU plugin are still required. The source submodule
is never modified.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ORIGINAL = """if(WIN32)
    add_executable(fable_2 WIN32 ${FABLE2_SOURCES})
else()
    add_executable(fable_2 ${FABLE2_SOURCES})
endif()"""

REPLACEMENT = """if(ANDROID)
    if(NOT FABLE2_PORT_ROOT OR NOT EXISTS "${FABLE2_PORT_ROOT}/android/native/fable2_touch.cpp")
        message(FATAL_ERROR "Set -DFABLE2_PORT_ROOT to the absolute Fteste/port path")
    endif()
    # Guest sources must exist at configure time, or the app would be built
    # with NO recompiled Fable II code. Generate before running CMake.
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/sources.cmake")
        message(FATAL_ERROR "Fable II guest source list missing: run the host ReXGlue codegen first")
    endif()
    # Fable guest recompilation is linked into an SDL-loaded Android library.
    list(APPEND FABLE2_SOURCES
        ${FABLE2_PORT_ROOT}/android/native/fable2_touch.cpp)
    add_library(fable_2 SHARED ${FABLE2_SOURCES})
    set_target_properties(fable_2 PROPERTIES OUTPUT_NAME fable2)
elseif(WIN32)
    add_executable(fable_2 WIN32 ${FABLE2_SOURCES})
else()
    add_executable(fable_2 ${FABLE2_SOURCES})
endif()"""

GPU_ORIGINAL = "rexglue_setup_target(fable_2 GPU_PLUGINS xenos)"
GPU_REPLACEMENT = """if(ANDROID)
    # Renderer is built separately by port/gpu/CMakeLists.txt with Fable II
    # shader data. Do not ask ReXGlue's SDK stage step for a nonexistent
    # stock GPU plugin: it only knows its own prebuilt backends.
    rexglue_setup_target(fable_2)
    # The generated guest object library is linked into libfable2.so.
    # Android/aarch64 shared libraries require position-independent code.
    if(NOT TARGET fable_2_recomp)
        message(FATAL_ERROR "Codegen provided no fable_2_recomp target; refusing a launcher-only build")
    endif()
    set_target_properties(fable_2_recomp PROPERTIES POSITION_INDEPENDENT_CODE ON)
else()
    rexglue_setup_target(fable_2 GPU_PLUGINS xenos)
endif()"""

GPU_CONFIG_OLD = 'std::string plugin = config.gpu_plugin.empty() ? "xenos" : config.gpu_plugin;'
GPU_CONFIG_NEW = '''#if defined(__ANDROID__)
    // Use the Android Vulkan plugin name, never default to desktop Xenos D3D12.
    // A Fable-compatible Plume plugin MUST be built separately.
    std::string plugin = config.gpu_plugin.empty() ? "plume" : config.gpu_plugin;
#else
    std::string plugin = config.gpu_plugin.empty() ? "xenos" : config.gpu_plugin;
#endif'''

PATH_START_OLD = '''    const std::filesystem::path exe_dir =
        rex::filesystem::GetExecutableFolder();'''
# The same exe_dir declaration also appears in OnPostInitLogging(). Only
# replace the one inside OnConfigurePaths(), not every identical declaration.
PATH_CONFIG_ORIGINAL = '  void OnConfigurePaths(rex::PathConfig& paths) override {\n' + PATH_START_OLD
PATH_START_NEW = '''    const std::filesystem::path exe_dir =
        rex::filesystem::GetExecutableFolder();
#if defined(__ANDROID__)
    // SDLActivity sets this to the imported game tree in app-specific storage.
    if (paths.game_data_root.empty()) {
      if (const char* env = std::getenv("FABLE2_GAME_ROOT"); env && *env) {
        paths.game_data_root = env;
      }
    }
#endif'''

CONFIG_LOAD_OLD = '    fable2::config::Load(exe_dir / "fable2_config.toml");'
CONFIG_LOAD_NEW = '''#if defined(__ANDROID__)
    // The .so/plugin directory is read-only on Android. Keep this file beside
    // writable saves/cache, as configured by the SDLActivity before SDL_main.
    const char* user_root = std::getenv("FABLE2_USER_ROOT");
    if (!user_root || !*user_root) {
      REXSYS_ERROR("FABLE2_USER_ROOT is required on Android");
      std::exit(1);
    }
    const std::filesystem::path settings_dir(user_root);
    std::error_code settings_ec;
    std::filesystem::create_directories(settings_dir, settings_ec);
    if (settings_ec) {
      REXSYS_ERROR("Cannot create writable Fable II settings directory: {}", settings_ec.message());
      std::exit(1);
    }
    fable2::config::Load(settings_dir / "fable2_config.toml");
#else
    fable2::config::Load(exe_dir / "fable2_config.toml");
#endif'''

PATH_STORAGE_OLD = '''    std::error_code ec;
    paths.user_data_root = exe_dir / "saves";
    std::filesystem::create_directories(paths.user_data_root, ec);
    paths.cache_root = exe_dir / "cache";
    std::filesystem::create_directories(paths.cache_root, ec);'''
PATH_STORAGE_NEW = '''    std::error_code ec;
#if defined(__ANDROID__)
    // The APK/nativeLibraryDir is read-only. Saves/cache must never go there.
    std::filesystem::path writable_root = paths.game_data_root.parent_path();
    if (const char* env = std::getenv("FABLE2_USER_ROOT"); env && *env) {
      writable_root = env;
    }
    paths.user_data_root = writable_root / "saves";
    paths.cache_root = writable_root / "cache";
#else
    paths.user_data_root = exe_dir / "saves";
    paths.cache_root = exe_dir / "cache";
#endif
    std::filesystem::create_directories(paths.user_data_root, ec);
    ec.clear();
    std::filesystem::create_directories(paths.cache_root, ec);'''

# Fable's desktop CMake stages .cmd launchers and injects debug Lua files into
# data/. On Android these must not be copied into nativeLibraryDir or into a
# proprietary input tree. Keep desktop behavior on desktop only.
DESKTOP_STAGING_START = '# Stage a copy of the README + the function-tracing launcher next to the exe'
DESKTOP_STAGING_END = '# --- Recomp user config (fable2_config.toml) -------------------------------'
DESKTOP_ARTWORK_START = 'add_custom_command(TARGET fable_2 POST_BUILD\n    COMMAND ${CMAKE_COMMAND} -E copy_if_different\n            "${CMAKE_CURRENT_SOURCE_DIR}/assets/app-icon.png"'
DESKTOP_ARTWORK_END = '# --- Vulkan renderer: Stage 2 (source-built plugin, swappable at launch) --'

WIN_DIAGNOSTICS = ('fable2_av_probe.h', 'fable2_stall_dump.h')


def exactly_once(text: str, before: str, after: str, what: str) -> str:
    amount = text.count(before)
    if amount != 1:
        raise ValueError(f"{what}: expected one upstream anchor, found {amount}; upstream changed")
    return text.replace(before, after)


def replace_target(content: str) -> str:
    result = exactly_once(content, ORIGINAL, REPLACEMENT, "native target")
    result = exactly_once(result, GPU_ORIGINAL, GPU_REPLACEMENT, "GPU setup")
    if DESKTOP_STAGING_START in result or DESKTOP_STAGING_END in result:
        result = patch_desktop_staging(result)
    if DESKTOP_ARTWORK_START in result or DESKTOP_ARTWORK_END in result:
        result = patch_desktop_artwork(result)
    return result


def patch_desktop_staging(content: str) -> str:
    if content.count(DESKTOP_STAGING_START) != 1 or content.count(DESKTOP_STAGING_END) != 1:
        raise ValueError('CMake desktop staging anchors changed; review upstream before patching')
    start = content.index(DESKTOP_STAGING_START)
    end = content.index(DESKTOP_STAGING_END)
    middle = content[start:end]
    return content[:start] + 'if(NOT ANDROID)\n' + middle + 'endif() # NOT ANDROID: desktop script/Lua staging\n\n' + content[end:]


def patch_desktop_artwork(content: str) -> str:
    if content.count(DESKTOP_ARTWORK_START) != 1 or content.count(DESKTOP_ARTWORK_END) != 1:
        raise ValueError('CMake desktop asset anchors changed; review upstream before patching')
    start = content.index(DESKTOP_ARTWORK_START)
    end = content.index(DESKTOP_ARTWORK_END)
    return (content[:start] + 'if(NOT ANDROID)\n' + content[start:end]
            + 'endif() # NOT ANDROID: desktop app icon/command file\n\n' + content[end:])


def patch_app(content: str) -> str:
    content = exactly_once(content, GPU_CONFIG_OLD, GPU_CONFIG_NEW, "GPU default")
    content = exactly_once(content, CONFIG_LOAD_OLD, CONFIG_LOAD_NEW, "writable config")
    # OnConfigurePaths is the only hook that can use paths.game_data_root.
    content = exactly_once(content, PATH_CONFIG_ORIGINAL,
                           '  void OnConfigurePaths(rex::PathConfig& paths) override {\n' + PATH_START_NEW,
                           "OnConfigurePaths data path")
    return exactly_once(content, PATH_STORAGE_OLD, PATH_STORAGE_NEW, "writable user data")


def patch_main(content: str) -> str:
    for name in WIN_DIAGNOSTICS:
        include = f'#include "{name}"'
        guarded = f'#ifdef _WIN32\n{include}\n#endif  // _WIN32'
        content = exactly_once(content, include, guarded, f"Windows-only {name}")
    return content


def excluded(_directory: str, names: list[str]) -> set[str]:
    # Do not copy working game dumps, generated binaries or .git state.
    forbidden = {".git", "data", "out", "build", "build-android", ".vs", "cache", "saves", "logs", "rexglue-sdk"}
    extensions = (".iso", ".xex", ".god", ".apk", ".aab", ".so", ".dll", ".exe")
    return {name for name in names if name in forbidden or name.lower().endswith(extensions)}


def prepare(source: Path, output: Path, port_root: Path) -> list[str]:
    source, output, port_root = source.resolve(), output.resolve(), port_root.resolve()
    if not (source / "CMakeLists.txt").is_file():
        raise ValueError("Fable-2-Recomp missing. Run git submodule update --init --recursive")
    if not (port_root / 'android/native/fable2_touch.cpp').is_file():
        raise ValueError("Android native touch source missing")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Worktree must not overwrite or be nested inside original submodule")
    if output.exists():
        raise ValueError(f"Output already exists: {output}; remove manually to regenerate")

    # Validate all upstream patterns BEFORE creating any output.
    transformations = {
        Path('CMakeLists.txt'): replace_target,
        Path('src/core/fable_2_app.h'): patch_app,
        Path('src/main.cpp'): patch_main,
    }
    patched = {}
    for relative, transform in transformations.items():
        path = source / relative
        if not path.is_file():
            raise ValueError(f"Upstream file is missing: {relative}")
        patched[relative] = transform(path.read_text(encoding='utf-8'))

    shutil.copytree(source, output, ignore=excluded, symlinks=False)
    for relative, contents in patched.items():
        (output / relative).write_text(contents, encoding="utf-8")
    # The port path must be passed explicitly to CMake, not baked into source.
    return [str(relative) for relative in transformations]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('external/Fable-2-Recomp'))
    parser.add_argument('--output', type=Path, default=Path('build/fable2-android-worktree'))
    parser.add_argument('--port-root', type=Path, default=Path('port'))
    args = parser.parse_args()
    try:
        files = prepare(args.source, args.output, args.port_root)
    except ValueError as error:
        parser.error(str(error))
    print('[OK] Created isolated Android Fable II worktree: ' + str(args.output))
    print('[OK] Patched: ' + ', '.join(files))
    print('[REQUIRED] Pass -DFABLE2_PORT_ROOT=<repo>/port to CMake with Android NDK')
    print('[BLOCKED] Compatible SDK codegen, full GPU renderer and game data still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
