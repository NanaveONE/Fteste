import sys
from pathlib import Path
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install_fable_plume46 as p

SHELL = '''plume_overlay="$root/build/fable2-plume-overlay-v2"
python3 "$root/scripts/prepare_fable_plume.py" \\
  --xerenge-root "$root/external/Xerenge" --output "$plume_overlay"
build="$root/build/fable2-gpu-android-arm64"
  -DFABLE2_PLUME_DRAW_CPP="$plume_overlay/plume_draw.cpp" \\
'''
CMAKE = 'target_compile_definitions(rexgpu-plume PRIVATE XERENGE_HAS_SHADER_CACHE=1 FABLE2_PLUME_PORT=1)'

class Installer(unittest.TestCase):
 def test_shell_install(self):
  out=p.patch_shell(SHELL)
  self.assertIn('--base-overlay',out)
  self.assertIn('FABLE2_PLUME_OVERLAY_DIR',out)
  self.assertNotIn('\nplume_overlay="$root/build/fable2-plume-overlay-v2"',out)
 def test_cmake(self):
  out=p.patch_cmake(CMAKE)
  self.assertIn('target_include_directories(rexgpu-plume BEFORE PRIVATE',out)
  self.assertIn('fable2',p.patch_cmake(CMAKE).lower())
 def test_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/'scripts').mkdir(); (root/'port/gpu').mkdir(parents=True)
   first=root/'scripts/build_fable_gpu.sh';second=root/'port/gpu/CMakeLists.txt'
   first.write_text('unrecognized version');second.write_text(CMAKE)
   with self.assertRaises(ValueError):p.run(root)
   self.assertEqual(second.read_text(),CMAKE)
 def test_idempotence_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/'scripts').mkdir();(root/'port/gpu').mkdir(parents=True)
   first=root/'scripts/build_fable_gpu.sh';second=root/'port/gpu/CMakeLists.txt'
   first.write_text(SHELL);second.write_text(CMAKE)
   p.run(root)
   with self.assertRaisesRegex(ValueError,'Already installed'):
    p.run(root)

if __name__=='__main__':unittest.main()
