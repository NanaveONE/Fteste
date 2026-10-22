"""Offline regression tests. Synthetic XEX and Codegen output only."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from scripts.generate_fable2_cpp_private import (
    codegen_artifact, compatible_xex, generate, official_manifest, preflight,
    relative_name,
)


class CodegenPrivate23Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'Fteste'
        self.source = self.repo / 'external/Fable-2-Recomp'
        self.source.mkdir(parents=True)
        (self.source / 'generated').mkdir()
        (self.source / 'generated/rexglue.cmake').write_text('# ReXGlue\n')
        (self.source / 'CMakeLists.txt').write_text('# fable_2\n')
        (self.source / 'fable_2_manifest.toml').write_text(
            '[project]\nname="fable_2"\ngame_root="."\nsdk_version="0.10.0"\n'
            '[entrypoint]\nfile_path="default.xex"\nout_directory_path="generated/default"\n'
            'includes=["fable2_switch_tables.toml"]\n')
        (self.source / 'fable2_switch_tables.toml').write_text('[[switch_tables]]\naddress=123\nregister=9\nlabels=[20]\n')
        self.game = self.repo / 'game-input'
        self.game.mkdir()
        self.xex = self.game / 'default.xex'
        self.xex.write_bytes(b'XEX2-private-test-only')
        sha = hashlib.sha256(self.xex.read_bytes()).hexdigest()
        catalog = self.source / 'constants/game_versions.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({'versions': [
            {'id': 'goty-us-eu', 'hash': sha, 'xexSize': self.xex.stat().st_size, 'compatible': True}]}))
        self.toolbase = self.repo / 'host-tools'
        self.toolbase.mkdir()
        self.tool = self.toolbase / 'rexglue'
        hdr = bytearray(48)
        hdr[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', hdr, 18, 62)
        self.tool.write_bytes(hdr)
        self.tool.chmod(0o755)
        self.lib = self.toolbase / 'librexruntime.so'
        self.lib.write_bytes(b'FAKE-HOST-LIB')
        (self.toolbase / 'codegen-report.json').write_text(json.dumps({
            'kind': 'linux_x86_64_rexglue_codegen', 'game_files_included': False,
            'sdk_git_commit': 'test-sdk-sha',
            'files': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                               'bytes': p.stat().st_size} for p in (self.tool, self.lib)}
        }))
        self.out = self.repo / 'build/fable2-guest-codegen-private'

    def plan(self):
        return preflight(self.repo, self.source, self.xex, self.tool, self.out)

    def test_official_manifest_and_supported_xex(self):
        names, config = official_manifest(self.source)
        self.assertEqual({p.name for p in names}, {'fable_2_manifest.toml', 'fable2_switch_tables.toml'})
        self.assertEqual(config['project']['name'], 'fable_2')
        self.assertEqual(compatible_xex(self.xex, self.source)[0], 'goty-us-eu')
        self.assertEqual(self.plan()['sdk_git_commit'], 'test-sdk-sha')
        self.assertFalse(self.out.exists())

    def test_rejects_xex_changed_or_unsupported(self):
        self.xex.write_bytes(b'XEX2-not-the-same')
        with self.assertRaisesRegex(ValueError, 'not a supported'):
            self.plan()
        self.xex.write_bytes(b'NOTXEX')
        with self.assertRaisesRegex(ValueError, 'genuine'):
            self.plan()

    def test_rejects_corrupt_host_artifact_and_wrong_arch(self):
        self.lib.write_bytes(b'CORRUPT')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            codegen_artifact(self.tool)
        self.lib.write_bytes(b'FAKE-HOST-LIB')
        data = bytearray(self.tool.read_bytes())
        struct.pack_into('<H', data, 18, 183)
        self.tool.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'x86_64'):
            codegen_artifact(self.tool)

    def test_preflight_rejects_public_or_preexisting_output(self):
        with self.assertRaisesRegex(ValueError, 'under Fteste/build'):
            preflight(self.repo, self.source, self.xex, self.tool, self.repo / 'generated')
        self.out.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.plan()

    def test_rejects_manifest_mismatch_and_include_escape(self):
        manifest = self.source / 'fable_2_manifest.toml'
        original = manifest.read_text()
        manifest.write_text(original.replace('game_root="."', 'game_root="/tmp"'))
        with self.assertRaisesRegex(ValueError, 'manifest layout'):
            official_manifest(self.source)
        manifest.write_text(original.replace('fable2_switch_tables.toml', '../fable2_switch_tables.toml'))
        with self.assertRaisesRegex(ValueError, 'must be included'):
            official_manifest(self.source)
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            relative_name('../outside')

    def test_generates_only_in_private_gitignored_build(self):
        plan = self.plan()
        calls = []
        def fake_runner(cmd, **kw):
            calls.append(cmd)
            if cmd[1] == 'codegen':
                output = kw['cwd'] / 'generated/default'
                output.mkdir(parents=True)
                (output / 'unit-000.cpp').write_text('void actual_cpp_fixture() {}\n')
                (output / 'sources.cmake').write_text('set(GENERATED_SOURCES unit-000.cpp)\n')
            return mock.Mock(returncode=0)
        with mock.patch('platform.system', return_value='Linux'), \
             mock.patch('platform.machine', return_value='x86_64'):
            report = generate(plan, runner=fake_runner)
        self.assertEqual(report['state'], 'GUEST_CPP_GENERATED')
        self.assertEqual(report['translation_units'], 1)
        self.assertEqual(calls[1][1:], ['codegen', 'fable_2_manifest.toml'])
        self.assertEqual((self.out / 'default.xex').read_bytes(), self.xex.read_bytes())
        self.assertEqual((self.source / 'fable_2_manifest.toml').read_bytes(),
                         (self.out / 'fable_2_manifest.toml').read_bytes())
        self.assertNotIn('XEX2', (self.out / 'codegen-summary.json').read_text())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.plan()

    def test_fails_on_missing_cpp_after_tool_returns_success(self):
        plan = self.plan()
        def success_without_files(cmd, **kw):
            return mock.Mock(returncode=0)
        with mock.patch('platform.system', return_value='Linux'), \
             mock.patch('platform.machine', return_value='x86_64'):
            with self.assertRaisesRegex(ValueError, 'sources.cmake'):
                generate(plan, runner=success_without_files)
        self.assertTrue((self.out / 'codegen.log').is_file())
        self.assertFalse((self.out / 'codegen-summary.json').exists())

    def test_not_for_termux_arm64(self):
        plan = self.plan()
        with mock.patch('platform.system', return_value='Linux'), \
             mock.patch('platform.machine', return_value='aarch64'):
            with self.assertRaisesRegex(ValueError, 'Linux x86_64'):
                generate(plan)
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
