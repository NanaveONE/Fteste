import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(filename,what):
    spec=importlib.util.spec_from_file_location(what,ROOT/'scripts'/filename)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

patch=load('apply_fable_plume53.py','plume53')
installer=load('install_fable_plume53.py','install53')
upgrader=load('upgrade_fable_memexport53_private.py','private53')
# Fictional, source-free Plume52 placeholders for deterministic exact-anchor tests.
HEADER='''  void FinishMemExport52();
  std::unique_ptr<plume::RenderBuffer> memexport52_stats_;
  void* memexport52_stats_mapped_ = nullptr;
'''
DRAW='''#include "fable_memexport52.h"
  draw_set_builder_.addReadWriteByteAddressBuffer(9);
  memexport52_stats_mapped_ = nullptr;
  memexport52_stats_.reset();
  memexport52_enabled_ = want_memexport52;
    made.set->setBuffer(fable2::memexport52::kStatsDescriptorIndex,
                        memexport52_stats_.get(), fable2::memexport52::kStatsBytes);
PlumeDrawContext::~PlumeDrawContext() {
}
'''
GRAPHICS='''  if (draw_context_) draw_context_->FinishMemExport52();
'''

class MemExport53(unittest.TestCase):
    def test_storage_and_fence(self):
        d=patch.patch_draw(DRAW)
        self.assertIn('addReadWriteByteAddressBuffer(10)',d)
        self.assertIn('RenderBufferDesc::ReadbackBuffer',d)
        self.assertIn('kJournalDescriptorIndex',d)
        self.assertIn('FinishMemExport53()',d)
        self.assertIn('guest RAM commit DISABLED',d)
        self.assertNotIn('memory->TranslatePhysical(',d)
        self.assertNotIn('memexport53::Commit(',d)
        self.assertIn('memexport53_journal_',patch.patch_header(HEADER))
        self.assertIn('FinishMemExport53()',patch.patch_graphics(GRAPHICS))
    def test_anchor_fail_closed(self):
        for fn,data in ((patch.patch_draw,DRAW),(patch.patch_header,HEADER),(patch.patch_graphics,GRAPHICS)):
            with self.assertRaises(ValueError):fn(data+data)
            with self.assertRaises(ValueError):fn('changed upstream')
    def test_manifest_idempotence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); upstream=root/'Xerenge';upstream.mkdir()
            base=root/'52';base.mkdir()
            (base/'plume_draw.cpp').write_text(DRAW)
            (base/'plume_graphics_system.cpp').write_text(GRAPHICS)
            (base/'plume_renderer').mkdir()
            (base/'plume_renderer/plume_draw.h').write_text(HEADER)
            output=root/'53'
            self.assertEqual(patch.prepare(upstream,base,output)['patch'],53)
            self.assertEqual(patch.prepare(upstream,base,output)['patch'],53)
            self.assertEqual(list(upstream.iterdir()),[])
            (output/'plume_draw.cpp').write_text('tamper')
            with self.assertRaises(ValueError):patch.prepare(upstream,base,output)
    def test_installer(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'scripts').mkdir()
            path=root/'scripts/build_fable_gpu.sh'
            path.write_text('start\n'+installer.BEFORE+'\nend\n')
            with self.assertRaises(ValueError):installer.run(root,True)
            installer.run(root,False)
            installer.run(root,True)
            installer.run(root,False)
            self.assertEqual(path.read_text().count(installer.MARK),1)
    def test_private_transformation(self):
        before=(upgrader.DECLARATION+'\nvoid X() {\n'+upgrader.ORIGINAL+'\n}\n')
        after=upgrader.transform(before)
        self.assertEqual(after.count('[[vk::binding(10, 0)]]'),1)
        self.assertIn('InterlockedAdd(12u, 1u',after)
        self.assertIn('Store4(fable_offset + 8u',after)
        self.assertLess(after.index('InterlockedAdd(12u'),after.index('g_FableMemExportMemory51.Store4'))
        with self.assertRaises(ValueError):upgrader.transform(after)
        with self.assertRaises(ValueError):upgrader.transform(before+before)

if __name__=='__main__':unittest.main()
