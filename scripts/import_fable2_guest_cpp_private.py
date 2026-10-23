#!/usr/bin/env python3
"""Import the user's generated Fable II C++ into a gitignored Android worktree.

This does NOT publish, build, or recompile proprietary game code.
Only the pinned Fable-2-Recomp/GOTY archive is accepted. The private generated
CMake is guarded so Android CMake NEVER tries to execute an Android codegen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import shutil
import sys
import tempfile
import zipfile

EXPECTED_TITLE = 'Fable II'
EXPECTED_XEX = '88c4ef2e18e65409444d1b068eff921d1f7e180a5ae64edc64ba6b0872372662'
EXPECTED_RECOMP = 'a4b0274e67d82514d44b42ac9320c30dc93bdaa3'
MAX_UNPACKED_BYTES = 700 * (1 << 20)
MAX_FILES = 800
SOURCE_RE = re.compile(r'\$\{CMAKE_CURRENT_LIST_DIR\}/(fable_2_(?:recomp\.\d+|init|register)\.cpp)')
ALLOWED_GENERATED = re.compile(r'generated/default/[A-Za-z0-9_.-]+\.(?:cpp|h|cmake|json)')
FREEZE_MARKER = 'FABLE2_PRIVATE_CPP_IMPORTED'
CMD_ANCHOR = ('add_custom_command(\n'
              '    OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"')
CODEGEN_END = '\n# Include DLL module shared library targets'


class Blocked(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def private_cmake(content: str) -> str:
    """Preserve original codegen rule, but disable it for imported guest C++."""
    if FREEZE_MARKER in content:
        # Accept only our own idempotent wrapper.
        if 'add_custom_target(fable_2_codegen)' in content and 'if(FABLE2_PRIVATE_CPP_IMPORTED)' in content:
            return content
        raise Blocked('Unexpected existing private-codegen CMake modification')
    if content.count(CMD_ANCHOR) != 1 or content.count(CODEGEN_END) != 1:
        raise Blocked('Generated CMake codegen anchors changed; review SDK generator output')
    start = content.index(CMD_ANCHOR)
    stop = content.index(CODEGEN_END, start)
    old = content[start:stop]
    if old.count('add_custom_target(fable_2_codegen') != 1 or 'DEPFILE ' not in old:
        raise Blocked('Generated CMake custom command is not recognized')
    wrapper = (
        'option(FABLE2_PRIVATE_CPP_IMPORTED "Use verified, private Fable II generated C++" OFF)\n'
        'if(FABLE2_PRIVATE_CPP_IMPORTED)\n'
        '    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp")\n'
        '        message(FATAL_ERROR "Private guest C++ was not imported/verified")\n'
        '    endif()\n'
        '    # Never regenerate the imported commercial guest sources during a cross-build.\n'
        '    add_custom_target(fable_2_codegen)\n'
        'else()\n'
    )
    wrapper += old + '\nendif() # FABLE2_PRIVATE_CPP_IMPORTED\n'
    return content[:start] + wrapper + content[stop:]


def _read_archive(archive: Path, xex: Path, manifest: Path) -> tuple[dict, dict, dict, str]:
    if sha256_file(xex) != EXPECTED_XEX:
        raise Blocked('default.xex does not match compatible original GOTY USA/EU')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
            raise Blocked('Oversized or unexpected generated code archive')
        files = {}
        for info in infos:
            name = info.filename
            pure = PurePosixPath(name)
            if (info.is_dir() or name.startswith('/') or '\\' in name
                    or '..' in pure.parts or '.' in pure.parts or str(pure) != name
                    or ((info.external_attr >> 16) & 0o170000) == 0o120000):
                raise Blocked(f'Unsafe ZIP entry: {name}')
            if name in files:
                raise Blocked(f'Duplicate ZIP entry: {name}')
            if not (ALLOWED_GENERATED.fullmatch(name) or name == 'generated/rexglue.cmake'
                    or name in ('VALIDACAO-24.json', 'codegen-summary.json', 'README-PRIVADO-24.txt')):
                raise Blocked(f'Unexpected private archive member: {name}')
            files[name] = info
        for required in ('generated/default/sources.cmake', 'generated/rexglue.cmake',
                         'codegen-summary.json', 'VALIDACAO-24.json'):
            if required not in files:
                raise Blocked('Incomplete generated archive: ' + required)
        summary = json.loads(z.read('codegen-summary.json'))
        validation = json.loads(z.read('VALIDACAO-24.json'))
        if (summary.get('state') != 'GUEST_CPP_GENERATED'
                or summary.get('xex_sha256') != EXPECTED_XEX
                or validation.get('guest_xex_sha256') != EXPECTED_XEX
                or validation.get('upstream_recomp_commit') != EXPECTED_RECOMP
                or validation.get('codegen_exit_status') != 0):
            raise Blocked('Archive provenance does not match pinned Fable II recomp and XEX')
        if summary.get('manifest_sha256') != sha256_file(manifest):
            raise Blocked('Manifest differs from one used to generate the guest C++')
        source_names = SOURCE_RE.findall(z.read('generated/default/sources.cmake').decode('utf-8'))
        source_set = {'generated/default/' + name for name in source_names}
        actual = {name for name in files if name.endswith('.cpp')}
        if (not source_set or len(source_set) != len(source_names) or source_set != actual
                or len(source_set) != summary.get('translation_units')
                or len(source_set) != validation.get('guest_cpp_files')
                or sum(files[name].file_size for name in source_set) != validation.get('guest_cpp_bytes')):
            raise Blocked('Guest C++ source list, file inventory or byte counts do not agree')
        for name in source_set:
            if files[name].file_size < 40:
                raise Blocked('Empty/truncated guest C++ file: ' + name)
        cmake = private_cmake(z.read('generated/rexglue.cmake').decode('utf-8'))
        return summary, validation, files, cmake


def import_sources(root: Path, worktree: Path, archive: Path, xex: Path,
                   sdk: Path | None = None) -> dict:
    root, worktree, archive, xex = (p.resolve() for p in (root, worktree, archive, xex))
    build_root = (root / 'build').resolve()
    if not worktree.is_relative_to(build_root) or worktree == build_root:
        raise Blocked('Worktree must be inside Fteste/build/ (gitignored private output)')
    manifest = worktree / 'fable_2_manifest.toml'
    if not (manifest.is_file() and (worktree / 'CMakeLists.txt').is_file()):
        raise Blocked('First prepare the isolated Fable-2-Recomp Android worktree')
    summary, _validation, members, cmake = _read_archive(archive, xex, manifest)
    if sdk is not None:
        sdk = sdk.resolve(strict=True)
        if not (sdk / 'CMakeLists.txt').is_file():
            raise Blocked('ReXGlue Android SDK source tree is missing CMakeLists.txt')
        result = subprocess.run(['git', '-C', str(sdk), 'rev-parse', 'HEAD'],
                                check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise Blocked('Cannot determine ReXGlue Android SDK revision')
        expected_sdk = summary.get('sdk_git_commit')
        if not expected_sdk or result.stdout.strip().lower() != expected_sdk.lower():
            raise Blocked('Android SDK revision differs from guest Codegen SDK. '
                          'Use the matching ReXGlue source revision: ' + str(expected_sdk))
    dest = worktree / 'generated/default'
    report = dest / 'private-import-report.json'
    archive_hash = sha256_file(archive)
    if dest.exists():
        if report.is_file() and json.loads(report.read_text()).get('archive_sha256') == archive_hash:
            # Never assume files have stayed intact after a prior import.
            with zipfile.ZipFile(archive) as z:
                verified = all(
                    (worktree / name).is_file() and
                    sha256_file(worktree / name) == hashlib.sha256(z.read(name)).hexdigest()
                    for name in members if name.startswith('generated/default/')
                )
            if verified and (dest / 'codegen.build.stamp').is_file() and PRIVATE_CMAKE_OK(
                worktree / 'generated/rexglue.cmake'
            ):
                return {'state': 'ALREADY_IMPORTED', 'guest_cpp': summary['translation_units'],
                        'archive_sha256': archive_hash}
        raise Blocked('Generated destination already exists and is not verified; inspect it before retrying')
    generated_dir = worktree / 'generated'
    generated_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.fable2-cpp-stage-', dir=worktree))
    installed = False
    try:
        with zipfile.ZipFile(archive) as z:
            for name in members:
                if not name.startswith('generated/default/'):
                    continue
                p = stage / name.removeprefix('generated/')
                p.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, p.open('wb') as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
        (stage / 'default/codegen.build.stamp').write_text(
            'Imported verified Fable II GOTY C++; codegen must be frozen during ARM64 build.\n',
            encoding='utf-8')
        (stage / 'default/private-import-report.json').write_text(json.dumps({
            'archive_sha256': archive_hash, 'game': EXPECTED_TITLE,
            'guest_cpp': summary['translation_units'], 'upstream_commit': EXPECTED_RECOMP,
            'note': 'PRIVATE generated code; do not commit or upload to GitHub',
        }, indent=2) + '\n')
        cmake_path = generated_dir / 'rexglue.cmake'
        # Atomic replacement of the generated integration. Everything is inside build/.
        replacement = stage / 'rexglue.cmake'
        replacement.write_text(cmake, encoding='utf-8')
        os.replace(replacement, cmake_path)
        os.replace(stage / 'default', dest)
        installed = True
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if not installed:
        raise Blocked('Private source import did not complete')
    return {'state': 'IMPORTED', 'guest_cpp': summary['translation_units'],
            'archive_sha256': archive_hash}


def PRIVATE_CMAKE_OK(path: Path) -> bool:
    return path.is_file() and 'if(FABLE2_PRIVATE_CPP_IMPORTED)' in path.read_text(encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--worktree', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--xex', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, help='Verify same ReXGlue Git commit used by Codegen')
    args = parser.parse_args()
    try:
        result = import_sources(args.repo_root, args.worktree, args.archive, args.xex, args.sdk)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print('BLOCKED: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    print('PRIVATE: guest files in build/ only. Run Android NDK CMake with '
          '-DFABLE2_PRIVATE_CPP_IMPORTED=ON; never upload generated/*.cpp.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
