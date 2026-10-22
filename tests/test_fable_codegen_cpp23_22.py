"""Regression tests for the Linux ReXGlue Codegen C++23 toolchain."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_fable_codegen_cpp23 import CPP23_SMOKE, clang_major, verify_toolchain

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build-fable-codegen-host.yml'


class CodegenCpp23Tests(unittest.TestCase):
    def test_clang_version_detects_ubuntu(self):
        self.assertEqual(clang_major('Ubuntu clang version 19.1.1 (Ubuntu 19.1.1-1)'), 19)
        self.assertEqual(clang_major('clang version 20.0.0'), 20)

    def test_clang_version_rejects_nonclang(self):
        with self.assertRaisesRegex(ValueError, 'not Clang'):
            clang_major('g++ (Ubuntu 13.3.0)')

    def test_smoke_contains_all_runtime_requirements(self):
        for symbol in ('<expected>', 'std::expected', 'std::unexpected',
                       '__cpp_concepts < 202002L', '__cpp_lib_expected',
                       'std::from_chars', 'std::jthread'):
            self.assertIn(symbol, CPP23_SMOKE)

    def test_workflow_installs_and_pins_clang19(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        for item in ('clang-19 libstdc++-13-dev',
                     'scripts/check_fable_codegen_cpp23.py',
                     '-DCMAKE_C_COMPILER=/usr/bin/clang-19',
                     '-DCMAKE_CXX_COMPILER=/usr/bin/clang++-19',
                     'CMAKE_CXX_COMPILER:(FILEPATH|STRING)=', 'libxss-dev',
                     '--target rexglue', 'fable2-rexglue-codegen-linux-x86_64'):
            self.assertIn(item, text)
        self.assertNotIn('sudo apt-get install -y clang ', text)

    def test_cmake_cache_can_use_string_or_filepath(self):
        import re
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('CMAKE_CXX_COMPILER:(FILEPATH|STRING)', text)
        expression = r'^CMAKE_CXX_COMPILER:(FILEPATH|STRING)=/usr/bin/clang\+\+-19$'
        for kind in ('STRING', 'FILEPATH'):
            self.assertRegex('CMAKE_CXX_COMPILER:' + kind + '=/usr/bin/clang++-19', expression)
        self.assertNotRegex('CMAKE_CXX_COMPILER:STRING=/usr/bin/clang++-18', expression)

    def test_local_host_build_uses_same_cpp23_toolchain(self):
        script = (ROOT / 'scripts/build_host_tools.sh').read_text()
        self.assertIn('check_fable_codegen_cpp23.py', script)
        self.assertIn('-DCMAKE_C_COMPILER=/usr/bin/clang-19', script)
        self.assertIn('-DCMAKE_CXX_COMPILER=/usr/bin/clang++-19', script)
        self.assertIn('CMAKE_CXX_COMPILER:(FILEPATH|STRING)', script)
        self.assertIn('find "$sdk/out/linux-amd64"', script)
        self.assertNotIn('find "$sdk/out/build/linux-amd64"', script)
        self.assertIn('--target xerenge_tool_dump_xex', script)

    def test_missing_compiler_fails_before_compile(self):
        with patch('scripts.check_fable_codegen_cpp23.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Missing clang-19'):
                verify_toolchain()

    def test_llvm18_fails_before_build(self):
        class FakeResult:
            returncode = 0
            stdout = 'Ubuntu clang version 18.1.3'
            stderr = ''
        with patch('scripts.check_fable_codegen_cpp23.shutil.which', return_value='/usr/bin/fake'), \
             patch('scripts.check_fable_codegen_cpp23.command_result', return_value=FakeResult()):
            with self.assertRaisesRegex(ValueError, 'Clang 18'):
                verify_toolchain()

    def test_cpp_smoke_compiles_locally_when_supported(self):
        # Do not require Clang 19 on the development host; compile the *same*
        # smoke program with the locally available GNU C++23 implementation.
        cxx = shutil.which('g++')
        if not cxx:
            self.skipTest('g++ unavailable locally')
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            src, exe = Path(td) / 'test.cpp', Path(td) / 'test'
            src.write_text(CPP23_SMOKE)
            run = subprocess.run([cxx, '-std=c++23', '-pthread', str(src), '-o', str(exe)],
                                 text=True, capture_output=True)
            if run.returncode:
                self.skipTest('local g++ lacks C++23 std::expected; CI uses clang++-19')
            test = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(test.returncode, 0, test.stderr)


if __name__ == '__main__':
    unittest.main()
