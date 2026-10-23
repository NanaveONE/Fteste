import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('fix32',Path(__file__).resolve().parents[1]/'scripts/enable_imgui_android_32.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Tests(unittest.TestCase):
 def test_patch_idempotent(self):
  source='build="$root/build/fable2-android-arm64"\n    '+"'-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics'"+' \\\n'
  result=mod.patch(source)
  self.assertIn('imgui_header=',result)
  self.assertIn('-I${imgui_dir}',result)
  self.assertEqual(mod.patch(result),result)
 def test_fail_closed(self):
  with self.assertRaises(ValueError):mod.patch('not a build script')
if __name__=='__main__':unittest.main()
