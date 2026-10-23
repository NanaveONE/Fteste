#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/enable_rexglue_runtime_16k_39.py'
spec = importlib.util.spec_from_file_location('enable39', SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

WORKFLOW = 'name: runtime\nsteps:\n' + mod.WORKFLOW_OLD
BUILD = ('#!/usr/bin/env bash\n' + mod.BUILD_REPO_ANCHOR +
         mod.BUILD_OLD + mod.BUILD_CHECK_ANCHOR)


class Patch39Tests(unittest.TestCase):
    def test_patches_all_anchors(self):
        w, b = mod.transformed(WORKFLOW, BUILD)
        self.assertIn(mod.REXGLUE_REV, w)
        self.assertIn(mod.REXGLUE_REV, b)
        self.assertIn('ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', b)
        self.assertIn('max-page-size=16384', b)
        self.assertIn('check_android_16k_alignment.py', b)
        self.assertNotIn(mod.WORKFLOW_OLD, w)

    def test_idempotent(self):
        once = mod.transformed(WORKFLOW, BUILD)
        self.assertEqual(mod.transformed(*once), once)

    def test_partial_patch_rejected(self):
        w, b = mod.transformed(WORKFLOW, BUILD)
        with self.assertRaises(ValueError):
            mod.transformed(w, BUILD)
        with self.assertRaises(ValueError):
            mod.transformed(WORKFLOW, b)

    def test_stale_sdk_anchor_rejected(self):
        with self.assertRaises(ValueError):
            mod.transformed(WORKFLOW, BUILD.replace('REXGLUE_ARM64_MARCH', 'DIFFERENT'))

    def test_disk_application(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workflow = root / '.github/workflows/build-android-runtime.yml'
            build = root / 'scripts/build_rexglue_android_sdk.sh'
            workflow.parent.mkdir(parents=True)
            build.parent.mkdir(parents=True)
            workflow.write_text(WORKFLOW)
            build.write_text(BUILD)
            self.assertEqual(mod.apply(root), 'patched')
            self.assertEqual(mod.apply(root), 'already patched')


if __name__ == '__main__':
    unittest.main()
