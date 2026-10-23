import sys
from pathlib import Path
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import apply_fable_plume46 as p

class Patch46(unittest.TestCase):
 def test_changes_all_interfaces(self):
  hd='''  SharedWords<192> fetch_constants;\n  std::unique_ptr<plume::RenderBuffer> shared_constants_;\n  void* shared_constants_mapped_ = nullptr;'''
  sys=p.patch_header(hd)
  self.assertIn('fable_loop_words',sys)
  self.assertIn('fable_loop_constants_mapped_',sys)
  src='''  constants_as_last_[0] = constants_as_last_[1] = constants_as_last_[2] = true;'''
  self.assertIn('gpu_registers_[0x4908u + i]',p.patch_graphics(src))
 def test_draw_fail_closed(self):
  with self.assertRaisesRegex(ValueError,'upstream anchor'):
   p.patch_draw('unknown Plume version')
 def test_no_partial_file_writes(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t); overlay=root/'output';overlay.mkdir()
   (overlay/'plume_draw.cpp').write_text('no anchors')
   (overlay/'plume_graphics_system.cpp').write_text('no anchors')
   hd=root/'rexglue/src/plume_renderer/plume_draw.h';hd.parent.mkdir(parents=True)
   hd.write_text('header')
   with self.assertRaises(ValueError):p.prepare(root,overlay,root/"output46")
   self.assertFalse((overlay/'plume_renderer').exists())
 def test_not_pretending_memexport(self):
  self.assertNotIn('RWByteAddressBuffer',p.patch_graphics('  constants_as_last_[0] = constants_as_last_[1] = constants_as_last_[2] = true;'))

if __name__=='__main__':unittest.main()
