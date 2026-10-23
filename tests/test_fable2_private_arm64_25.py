"""Open-source-only tests. NO actual Fable II binaries/source are shipped."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import import_fable2_guest_cpp_private as imp
from enable_fable2_private_arm64 import patch_text, REPLACEMENTS, CODEGEN_START, CODEGEN_END, FINISH_ANCHOR

FAKE_CMAKE = (
    'before\n'
    'add_custom_command(\n'
    '    OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"\n'
    '    COMMAND rexglue codegen \n'
    '    DEPFILE "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.d"\n'
    ')\n'
    'add_custom_target(fable_2_codegen\n'
    '    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp")\n'
    '# Include DLL module shared library targets\n'
)


def create_archive(root: Path, *, bad_member: str = '', mismatch: bool = False) -> tuple[Path, Path, Path]:
    worktree = root / 'build/private-worktree'
    (worktree / 'generated').mkdir(parents=True)
    (worktree / 'CMakeLists.txt').write_text('project(fable_2)\n')
    manifest = worktree / 'fable_2_manifest.toml'
    manifest.write_text('[project]\nname="fable_2"\n')
    (worktree / 'generated/rexglue.cmake').write_text(FAKE_CMAKE)
    xex = root / 'default.xex'
    xex.write_bytes(b'fake Xbox game image -- not copyrighted content')
    digest = imp.sha256_file(xex)
    cpp = b'// synthetic C++ for tests only\nint fake_recomp() { return 7; }\n'
    summary = {
        'state': 'GUEST_CPP_GENERATED', 'xex_sha256': digest,
        'manifest_sha256': imp.sha256_file(manifest), 'translation_units': 1,
        'sdk_git_commit': '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b',
    }
    validation = {
        'guest_xex_sha256': digest,
        'upstream_recomp_commit': imp.EXPECTED_RECOMP,
        'codegen_exit_status': 0, 'guest_cpp_files': 1,
        'guest_cpp_bytes': len(cpp),
    }
    name = 'generated/default/fable_2_init.cpp'
    files = {
        'generated/default/sources.cmake': b'set(GENERATED_SOURCES\n    ${CMAKE_CURRENT_LIST_DIR}/fable_2_init.cpp\n)\n',
        name: cpp,
        'generated/default/fable_2_pch.h': b'#pragma once\n',
        'generated/rexglue.cmake': FAKE_CMAKE.encode(),
        'codegen-summary.json': json.dumps(summary).encode(),
        'VALIDACAO-24.json': json.dumps(validation).encode(),
    }
    if bad_member:
        files[bad_member] = b'bad entry!'
    if mismatch:
        files[name] = b'int broken = 1;'
    archive = root / 'private-cpp.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for member, content in files.items():
            z.writestr(member, content)
    return worktree, xex, archive


class ImportTests(unittest.TestCase):
    def test_real_structure_synthetic_import_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)):
                result = imp.import_sources(root, worktree, archive, xex)
                self.assertEqual(result['state'], 'IMPORTED')
                self.assertEqual(result['guest_cpp'], 1)
                self.assertIn('FABLE2_PRIVATE_CPP_IMPORTED', (worktree/'generated/rexglue.cmake').read_text())
                self.assertTrue((worktree/'generated/default/codegen.build.stamp').is_file())
                second = imp.import_sources(root, worktree, archive, xex)
                self.assertEqual(second['state'], 'ALREADY_IMPORTED')
                # Same-length tampering is rejected rather than silently reused.
                cpp = worktree/'generated/default/fable_2_init.cpp'
                contents = cpp.read_bytes()
                cpp.write_bytes(contents.replace(b'7;', b'9;'))
                with self.assertRaisesRegex(imp.Blocked, 'not verified'):
                    imp.import_sources(root, worktree, archive, xex)

    def test_wrong_xex_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            with self.assertRaisesRegex(imp.Blocked, 'default.xex does not match'):
                imp.import_sources(root, worktree, archive, xex)

    def test_manifest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            (worktree/'fable_2_manifest.toml').write_text('wrong manifest')
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)):
                with self.assertRaisesRegex(imp.Blocked, 'Manifest differs'):
                    imp.import_sources(root, worktree, archive, xex)

    def test_outside_ignored_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)):
                with self.assertRaisesRegex(imp.Blocked, 'inside Fteste/build'):
                    imp.import_sources(root, root/'external/Fable-2-Recomp', archive, xex)

    def test_sdk_revision_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            sdk = root / 'sdk'
            sdk.mkdir()
            (sdk/'CMakeLists.txt').write_text('project(rexglue)')
            from subprocess import CompletedProcess
            wrong = CompletedProcess(['git'], 0, stdout='0' * 40 + '\n', stderr='')
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)), \
                 patch.object(imp.subprocess, 'run', return_value=wrong):
                with self.assertRaisesRegex(imp.Blocked, 'revision differs'):
                    imp.import_sources(root, worktree, archive, xex, sdk)

    def test_sdk_revision_match_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root)
            sdk = root / 'sdk'
            sdk.mkdir()
            (sdk/'CMakeLists.txt').write_text('project(rexglue)')
            from subprocess import CompletedProcess
            right = CompletedProcess(['git'], 0,
                stdout='3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b\n', stderr='')
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)), \
                 patch.object(imp.subprocess, 'run', return_value=right):
                self.assertEqual(imp.import_sources(root, worktree, archive, xex, sdk)['state'],
                                 'IMPORTED')

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root, bad_member='../steal.txt')
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)):
                with self.assertRaisesRegex(imp.Blocked, 'Unsafe ZIP entry'):
                    imp.import_sources(root, worktree, archive, xex)

    def test_cpp_size_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree, xex, archive = create_archive(root, mismatch=True)
            with patch.object(imp, 'EXPECTED_XEX', imp.sha256_file(xex)):
                with self.assertRaisesRegex(imp.Blocked, 'byte counts'):
                    imp.import_sources(root, worktree, archive, xex)

    def test_generated_cmake_frozen_wrapper_preserves_original(self):
        result = imp.private_cmake(FAKE_CMAKE)
        self.assertIn('add_custom_target(fable_2_codegen)', result)
        self.assertIn('else()\nadd_custom_command(', result)
        self.assertEqual(imp.private_cmake(result), result)


class PatcherTests(unittest.TestCase):
    def synthetic_original(self):
        return ('\n'.join([before for before, _ in REPLACEMENTS[:4]]) + '\n'
                + CODEGEN_START + '\n'
                + '(cd "$work" && "$FABLE2_CODEGEN_TOOL" codegen "$work/fable_2_manifest.toml")\n'
                + '[[ -s "$work/generated/default/sources.cmake" ]] || exit 2\n'
                + CODEGEN_END + '\n'
                + '\n'.join([before for before, _ in REPLACEMENTS[4:]]) + '\n'
                + FINISH_ANCHOR + '\n')

    def test_patch_idempotence_and_private_branch(self):
        patched = patch_text(self.synthetic_original())
        self.assertEqual(patched, patch_text(patched))
        self.assertIn('import_fable2_guest_cpp_private.py', patched)
        self.assertIn('FABLE2_PRIVATE_CPP_IMPORTED="$private_cpp_mode"', patched)
        self.assertIn('ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', patched)
        self.assertIn('check_android_16k_alignment.py', patched)
        # Clear unsupported upstream alias/import mutation by passing an empty value.
        self.assertIn('    -DFABLE2_CODEGEN_TOOL= \\', patched)

    def test_unknown_upstream_refuses_to_patch(self):
        text = self.synthetic_original().replace('cmake', 'cmakk')
        with self.assertRaisesRegex(ValueError, 'anchor|Codegen'):
            patch_text(text)


if __name__ == '__main__':
    unittest.main()
