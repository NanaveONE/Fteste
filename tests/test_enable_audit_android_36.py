import importlib.util
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('enable36', ROOT/'scripts/enable_audit_android_36.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class TestEnable(unittest.TestCase):
 def test_integration_idempotent(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'build.sh'
   p.write_text(mod.ANCHOR+'\npython3 "$root/scripts/fix_fable2_frame_limiter_35.py" --worktree "$work"\n'+mod.OLD_BUILD+'\n')
   a=mod.apply(p)
   self.assertIn('audit_android_port_36.py',a)
   self.assertIn('-- -k 0',a)
   self.assertEqual(a, mod.apply(p))
 def test_missing_patch35_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'build.sh';p.write_text(mod.ANCHOR+'\n'+mod.OLD_BUILD)
   with self.assertRaises(ValueError): mod.apply(p)
