"""Validate the actual targeted shader-pipeline override and integrity rules."""
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
from scripts.prepare_fable_plume import (
    CULL_ANCHOR, CULL_PATCH, MISS_ANCHOR, MISS_PATCH, patch, prepare,
    patch_graphics_system, DUMP_ENABLE, DUMP_MKDIR, DUMP_DIR,
)


class FablePlumeOverlayTests(unittest.TestCase):
    @staticmethod
    def sample() -> str:
        return ('''// PlumeDrawContext::GetOrCreatePipeline\n'''
                + CULL_ANCHOR + '\n'
                + '''  // no other draw defaults are patched\n'''
                + MISS_ANCHOR + '\n')

    @staticmethod
    def graphics_sample() -> str:
        return ("#include <filesystem>\n#include <cstdlib>\n#include <fstream>\n"
                "#include <system_error>\n#include <cstdio>\n"
                "#define REXLOG_ERROR(...) ((void)0)\n"
                "void dump() {\n" + DUMP_ENABLE + "\n"
                "if (!dumping) return;\n"
                "std::error_code ec;\n" + DUMP_MKDIR + "\n"
                "char name[80];\n"
                "std::snprintf(name, sizeof(name), \"%s\", \"a\");\n" + DUMP_DIR + "\n"
                "auto path = dir / name;\n (void)path;\n }\n")

    def test_graphics_capture_dir_is_writable_and_opt_in(self):
        result = patch_graphics_system(self.graphics_sample())
        self.assertIn('FABLE2_DUMP_UCODE', result)
        self.assertIn('FABLE2_USER_ROOT', result)
        self.assertIn('"shader-captures" / "ucode-dump"', result)
        self.assertIn('#else\n  std::filesystem::create_directories("generated/ucode-dump", ec);', result)
        compiler = shutil.which('clang++') or shutil.which('g++')
        if compiler:
            with tempfile.TemporaryDirectory() as temp:
                cpp = Path(temp) / 'compile.cpp'
                cpp.write_text(result)
                for define in ([], ['-DFABLE2_PLUME_PORT=1']):
                    run = subprocess.run([compiler, '-std=c++20', '-fsyntax-only', *define, str(cpp)],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)

    def test_guest_culling_is_not_disabled_by_default(self):
        result = patch(self.sample())
        self.assertIn('FABLE2_DISABLE_GUEST_CULL', result)
        self.assertIn('FABLE2_PLUME_PORT', result)
        self.assertIn(CULL_PATCH, result)
        self.assertIn('cull = culling ? (cull & 7u) : 0u;', result)
        self.assertNotIn('FABLE2_DISABLE_GUEST_CULL=1', CULL_ANCHOR)

    def test_log_every_distinct_missing_pair_bounded(self):
        result = patch(self.sample())
        self.assertIn('FABLE2_MISSING_PIPELINE', result)
        self.assertIn('fable2_missing_pairs.size() < 1024', result)
        self.assertIn('fable2_missing_pairs.emplace(vs_hash, ps_hash)', result)
        self.assertEqual(result.count('FABLE2_MISSING_PIPELINE'), 1)
        self.assertIn(MISS_PATCH, result)

    def test_inserted_cpp_compiles_for_port_and_upstream_switch(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('No C++ compiler on this host')
        # Compile the exact injected C++ blocks with stub bindings, not a fake
        # game library. Does not claim the real renderer builds or runs.
        cpp = ("#include <set>\n#include <mutex>\n#include <cstdint>\n"
               "#include <cstdlib>\n#include <utility>\n"
               "#define REXLOG_WARN(...) ((void)0)\n"
               "void* render(uint64_t vs_hash, uint64_t ps_hash, uint32_t cull) {\n"
               + CULL_PATCH + "\n"
               "void* vs = nullptr; void* ps = nullptr;\n"
               + MISS_PATCH + "\nreturn nullptr;\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'port_gpu_syntax.cpp'
            path.write_text(cpp)
            for define in [[], ['-DFABLE2_PLUME_PORT=1']]:
                run = subprocess.run([compiler, '-std=c++20', '-fsyntax-only', *define, str(path)],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_do_not_silently_patch_a_new_unknown_upstream(self):
        with self.assertRaisesRegex(ValueError, 'upstream changed'):
            patch(self.sample().replace('XERENGE_CULL', 'XERENGE_NEW_CULL'))
        with self.assertRaisesRegex(ValueError, 'upstream changed'):
            patch(self.sample() + '\n' + MISS_ANCHOR)

    def test_original_and_worktree_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            upstream = base / 'upstream'
            input_path = upstream / 'rexglue/src/plume_renderer/plume_draw.cpp'
            input_path.parent.mkdir(parents=True)
            source = self.sample()
            input_path.write_text(source)
            graph = upstream / 'rexglue/src/plume_renderer/plume_graphics_system.cpp'
            graph.write_text(self.graphics_sample())
            output = base / 'build/fable2-plume-overlay'
            result = prepare(upstream, output)
            self.assertEqual(input_path.read_text(), source)
            patched = (output / 'plume_draw.cpp').read_text()
            self.assertEqual(result['patched_sha256'], __import__('hashlib').sha256(patched.encode()).hexdigest())
            self.assertIn('FABLE2_MISSING_PIPELINE', patched)
            self.assertEqual(prepare(upstream, output), result)
            input_path.write_text(source + '// new upstream change\n')
            with self.assertRaisesRegex(ValueError, 'out of date'):
                prepare(upstream, output)

    def test_never_write_inside_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            upstream = base / 'upstream'
            source = upstream / 'rexglue/src/plume_renderer/plume_draw.cpp'
            source.parent.mkdir(parents=True)
            source.write_text(self.sample())
            graph = upstream / 'rexglue/src/plume_renderer/plume_graphics_system.cpp'
            graph.write_text(self.graphics_sample())
            with self.assertRaisesRegex(ValueError, 'separate from'):
                prepare(upstream, upstream / 'generated-test')


if __name__ == '__main__':
    unittest.main()
