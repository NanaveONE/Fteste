"""Memgate72 regressions: only bounded opt-in scopes; no guest RAM commits."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def import_file(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

sdk72 = import_file('patch_rex_memgate72_sdk')
plume72 = import_file('apply_fable_plume72')


def fixture(sites, header):
    out = header+'\n'
    for anchor in sites:
        # The C++ body contains no extra parentheses so it can be checked by
        # text-transform tests independently of a private guest source.
        if anchor.endswith('{\n'):
            out += anchor+'  do_work();\n}\n'
        elif anchor.endswith(',\n'):
            out += anchor+'  extra_argument);\n}\n'
        else:
            out += 'void placeholder(){\n  '+anchor+'\n}\n'
    return out


class Memgate72SourceTests(unittest.TestCase):
    def test_runtime_real_ram_writes_and_mapping_scopes(self):
        sample = ('#include <rex/graphics/command_processor.h>\n'
                  + ''.join('void f(){\n  '+s+'\n}\n' for s, _, _ in sdk72.COMMAND)
                  + ''.join(s+'  return true;\n}\n' for s, _, _ in sdk72.COMMAND_FUNCTIONS))
        result = sdk72.modify(sdk72.FILES[0], sample)
        self.assertEqual(result.count('FABLE2_MEMGATE72_RUNTIME_HOOK'), 1)
        for _source, _kind, label in sdk72.COMMAND:
            self.assertEqual(result.count('fable72_'+label), 1)
        self.assertIn('FABLE_M71_DMA_MAPPING', result)
        self.assertIn('FABLE_M71_GPU_PRODUCER', result)
        with self.assertRaises(ValueError): sdk72.modify(sdk72.FILES[0], result)

    def test_integrity_check_reverses_known_sdk_hooks(self):
        sample = ('#include <rex/graphics/command_processor.h>\n'
                  + ''.join('void f(){\n  '+s+'\n}\n' for s, _, _ in sdk72.COMMAND)
                  + ''.join(sig+'  return true;\n}\n' for sig, _, _ in sdk72.COMMAND_FUNCTIONS))
        transformed = sdk72.modify(sdk72.FILES[0], sample)
        sdk72._validate_installed(sdk72.FILES[0], transformed)
        damaged = transformed.replace('fable72_mem_write', 'fable72_not_registered', 1)
        with self.assertRaises(ValueError):
            sdk72._validate_installed(sdk72.FILES[0], damaged)

    def test_runtime_xmemory_and_gpu_notification_scopes(self):
        for name, header, sites in (
            (sdk72.FILES[1], '#include <rex/system/xmemory.h>\n', sdk72.MEMORY_FUNCTIONS),
            (sdk72.FILES[2], '#include <rex/graphics/shared_memory.h>\n', sdk72.SHARED_FUNCTIONS)):
            sample = header + ''.join(signature+'  do_work();\n}\n' for signature, _, _ in sites)
            rewritten = sdk72.modify(name, sample)
            for _signature, _kind, label in sites:
                self.assertIn('fable72_'+label, rewritten)
            self.assertNotIn('fable_memexport_world61', rewritten)

    def test_reject_missing_or_duplicate_pinned_anchor(self):
        with self.assertRaises(ValueError): sdk72.modify(sdk72.FILES[0], 'changed SDK')
        snippet = sdk72.COMMAND[0][0]
        src = ('#include <rex/graphics/command_processor.h>\n'
               + '\n'.join(s for s, _, _ in sdk72.COMMAND)+'\n'+snippet)
        with self.assertRaises(ValueError): sdk72.modify(sdk72.FILES[0], src)

    def test_stage71_prerequisite_and_revision_pin(self):
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td)/'sdk'
            (tree/'src/graphics').mkdir(parents=True)
            (tree/'src/system').mkdir()
            (tree/'CMakeLists.txt').write_text('project(test)\n')
            for p in sdk72.FILES:
                (tree/p).write_text('not instrumented yet')
            with patch.object(sdk72.subprocess, 'check_output', return_value=sdk72.PIN+'\n'):
                with self.assertRaises(ValueError): sdk72.patch(tree)
            with patch.object(sdk72.subprocess, 'check_output', return_value='wrong\n'):
                with self.assertRaisesRegex(ValueError, 'revision'):
                    sdk72.patch(tree)

    def test_plume_real_graphics_worker_and_draw_scopes(self):
        graphic = ('#include <iostream>\n'
                   + ''.join(s+'  do_work();\n}\n' for s, _, _ in plume72.GRAPHICS_METHODS)
                   + '\n'.join(s for s, _ in plume72.GRAPHICS_CALLS))
        drawn = ('#include <iostream>\n'
                 + ''.join(s+'  do_work();\n}\n' for s, _, _ in plume72.DRAW_METHODS))
        changed = plume72.transform('plume_graphics_system.cpp', graphic)
        self.assertIn('fable72_gpu_capture_read', changed)
        self.assertIn('return CaptureGuestVideoFrame(&request, memory_);', changed)
        self.assertIn('fable72_present_worker', changed)
        self.assertIn('fable72_pm4_physical_write', changed)
        self.assertIn('fable72_read_pointer_writeback', changed)
        self.assertIn('fable72_pm4_execute', changed)
        self.assertIn('fable72_resolve_request', changed)
        self.assertIn('fable72_resolve_encoding', plume72.transform('plume_draw.cpp', drawn))
        with self.assertRaises(ValueError):
            plume72.transform('plume_graphics_system.cpp', changed)
        with self.assertRaises(ValueError):
            plume72.transform('plume_draw.cpp', 'not a real overlay')

    def test_overlay_staged_without_mutating_prior_or_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            build = Path(td)/'build'
            base = build/'fable2-plume-overlay-61'
            out = build/'fable2-plume-overlay-72'
            base.mkdir(parents=True)
            (base/'plume61-manifest.json').write_text('{}')
            (base/'plume_renderer').mkdir()
            (base/'plume_renderer/plume_draw.h').write_text('the private header stays identical')
            graphic = ('#include <iostream>\n'
                       + ''.join(s+'  do_work();\n}\n' for s, _, _ in plume72.GRAPHICS_METHODS)
                       + '\n'.join(s for s, _ in plume72.GRAPHICS_CALLS))
            draw = ('#include <iostream>\n'
                    + ''.join(s+'  do_work();\n}\n' for s, _, _ in plume72.DRAW_METHODS))
            (base/'plume_graphics_system.cpp').write_text(graphic)
            (base/'plume_draw.cpp').write_text(draw)
            with self.assertRaisesRegex(ValueError, 'not installed'):
                plume72.prepare(base, out, check=True)
            result = plume72.prepare(base, out)
            self.assertEqual(result['registered_scope_sites'], 7)
            self.assertFalse(result['memexport_commit_permitted'])
            self.assertFalse(result['vulkan_device_completion_covered'])
            self.assertEqual(plume72.prepare(base, out, check=True), result)
            self.assertEqual((base/'plume_graphics_system.cpp').read_text(), graphic)
            self.assertEqual((out/'plume_renderer/plume_draw.h').read_text(),
                             'the private header stays identical')
            (out/'plume_draw.cpp').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'drift'):
                plume72.prepare(base, out, check=True)

    def test_no_gpu_automatic_commit(self):
        for text in ((ROOT/'port/sdk/fable_memgate71.cpp').read_text(),
                     (ROOT/'port/gpu/fable_memgate71_gpu.cpp').read_text()):
            self.assertIn('return 0;', text) if 'fable_memgate71.cpp' in text else self.assertIn('fable_memgate71_commit_permitted()', text)
        src = (ROOT/'scripts/build_fable_gpu.sh').read_text()
        self.assertIn('apply_fable_plume72.py', src)
        self.assertIn('patch_rex_memgate72_sdk.py', src)
        self.assertIn('FABLE2_MEMGATE71_DIAGNOSTIC', src)
        self.assertIn('plume72-manifest.json', (ROOT/'port/gpu/CMakeLists.txt').read_text())
        self.assertIn('patch_rex_memgate72_sdk.py',
                      (ROOT/'scripts/build_rexglue_android_sdk.sh').read_text())

    def test_legacy_ci_accepts_exact_later_layers_only(self):
        module=import_file('normalize_fable_plume_build')
        for known in (module.STAGE71, module.STAGE72):
            current='prefix\n'+module.STAGE55_COMPOSED+known+'suffix\n'
            self.assertEqual(module.canonical_stage55(current),
                             'prefix\n'+module.STAGE55_LEGACY+module.RESTORED+'suffix\n')
            tampered=current.replace('patch_rex_memgate71_sdk.py',
                                     'patch_rex_unsafe_sdk.py', 1)
            with self.assertRaisesRegex(ValueError, 'Modified downstream'):
                module.canonical_stage55(tampered)
        self.assertEqual(module.canonical_stage55('old 55 script only'),
                         'old 55 script only')
        for name in ('install_fable_plume52.py', 'install_fable_plume53.py',
                     'install_fable_plume55.py'):
            self.assertIn('canonical_stage55', (ROOT/'scripts'/name).read_text())

    def test_stage55_rename_is_undone_only_after_full_suffix_check(self):
        module=import_file('normalize_fable_plume_build')
        full='prefix\n'+module.STAGE55_COMPOSED+module.STAGE72+'suffix\n'
        recovered=module.canonical_stage55(full)
        self.assertIn(module.STAGE55_LEGACY + module.RESTORED, recovered)
        self.assertNotIn('plume55_overlay=', recovered)
        # Changing either the earlier 55 variable or the later 72 hooks fails.
        for broken in (
                full.replace('plume55_overlay=', 'plume_overlay=', 1),
                full.replace('--overlay "$plume55_overlay"', '--overlay "$plume_overlay"', 1),
                full.replace('patch_rex_memgate72_sdk.py', 'patch_rex_untrusted_sdk.py', 1),
                full + module.STAGE72):
            with self.subTest(broken=broken[-85:]):
                with self.assertRaises(ValueError):
                    module.canonical_stage55(broken)
        with self.assertRaises(ValueError):
            module.canonical_stage55(module.STAGE55_COMPOSED+'suffix\n')

    def test_no_public_game_assets(self):
        workflow = (ROOT/'.github/workflows/test-fable-memgate72.yml').read_text()
        self.assertNotIn('actions/upload-artifact', workflow)
        self.assertNotIn('FABLE2_PRIVATE_TOKEN', workflow)


if __name__ == '__main__':
    unittest.main()
