import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def load(name, relative):
    source = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fix = load('fix37', 'scripts/fix_fable2_android_f5_lua_37.py')
enabler = load('enable37', 'scripts/enable_fable2_android_f5_lua_37.py')


class AndroidF5LuaTests(unittest.TestCase):
    def make_worktree(self, root):
        src = root / 'src'
        (src / 'input').mkdir(parents=True)
        (src / 'main.cpp').write_text('''// FTESTE_ANDROID_DIAGNOSTICS_33
#include "generated/default/fable_2_init.h"
#include "fable2_f5_lua.h"
#if !defined(__ANDROID__)
#include "fps_meter.h"
#endif  // !__ANDROID__
#include "fable_2_app.h"
''')
        (src / 'input' / 'keyboard_gamepad.h').write_text('''
void poll() {
#ifdef _WIN32
 fable2::f5lua::poll_f5();
#endif
}
''')

    def test_patch_and_idempotency(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make_worktree(root)
            self.assertEqual('patched', fix.patch(root))
            self.assertEqual('already patched', fix.patch(root))
            s = (root / 'src/main.cpp').read_text()
            self.assertIn(fix.REPLACEMENT, s)
            self.assertEqual(1, s.count('FTESTE_ANDROID_F5_LUA_37'))

    def test_fails_without_diagnostics_33(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make_worktree(root)
            p = root / 'src/main.cpp'
            p.write_text(p.read_text().replace('// FTESTE_ANDROID_DIAGNOSTICS_33', ''))
            with self.assertRaisesRegex(ValueError, 'patch 33'):
                fix.patch(root)

    def test_fails_if_keyboard_unguarded(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make_worktree(root)
            p = root / 'src/input/keyboard_gamepad.h'
            p.write_text('void poll() { fable2::f5lua::poll_f5(); }\n')
            with self.assertRaisesRegex(ValueError, 'no longer guarded'):
                fix.patch(root)

    def test_build_integration_once(self):
        old = '#!/bin/bash\n' + enabler.ANCHOR + '\necho build\n'
        new = enabler.enable(old)
        self.assertIn(enabler.COMMAND, new)
        self.assertEqual(new, enabler.enable(new))
        with self.assertRaises(ValueError):
            enabler.enable('#!/bin/bash\necho wrong anchor\n')

    def test_host_preprocessor_excludes_f5_on_android(self):
        cc = shutil.which('c++') or shutil.which('clang++')
        if not cc:
            self.skipTest('C++ compiler not installed')
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.make_worktree(root)
            fix.patch(root)
            source = (root / 'src/main.cpp').read_text()
            # Standalone preprocessor reproduction of main's include guards.
            filtered = '\n'.join(x for x in source.splitlines()
                                 if x.startswith('#if ') or x.startswith('#endif')
                                 or 'fable2_f5_lua.h' in x or 'fps_meter.h' in x)
            for android, expected in ((True, False), (False, True)):
                # Replace included headers with a sentinel to avoid SDK deps.
                text = filtered.replace('#include "fable2_f5_lua.h"', 'int f5_host_probe_present;')
                text = text.replace('#include "fps_meter.h"', 'int fps_meter_present;')
                flags = ['-D__ANDROID__'] if android else []
                result = subprocess.run([cc, '-x', 'c++', '-E', '-P', *flags, '-'],
                                        input=text, text=True, capture_output=True, check=True)
                self.assertEqual(expected, 'f5_host_probe_present' in result.stdout)
                self.assertEqual(expected, 'fps_meter_present' in result.stdout)


if __name__ == '__main__':
    unittest.main()
