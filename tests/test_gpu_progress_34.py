import importlib.util
import tempfile
from pathlib import Path
import unittest

script = Path(__file__).resolve().parents[1] / 'scripts/fix_fable2_gpu_progress_34.py'
spec = importlib.util.spec_from_file_location('fix34', script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Tests(unittest.TestCase):
    def test_patch_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / mod.REL
            f.parent.mkdir(parents=True)
            f.write_text('#include "fable_2_funcs.284.h"\nGetGlobalField_8221EE38(ctx, base);\nsub_82BA0E80(ctx, base);\n')
            self.assertEqual(mod.patch(Path(d)), 'patched')
            self.assertEqual(mod.patch(Path(d)), 'already patched')
            s = f.read_text()
            self.assertIn('extern "C" void GetGlobalField_8221EE38', s)
            self.assertNotIn('GetGlobalField_8221EE38(PPCContext& ctx, uint8_t* base) {', s)
    def test_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                mod.patch(Path(d))
if __name__ == '__main__':
    unittest.main()
