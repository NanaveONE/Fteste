import importlib.util
import tempfile
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,BASE/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

patch=load('scripts/apply_fable_plume52.py','patch52')
installer=load('scripts/install_fable_plume52.py','installer52')
installer53=load('scripts/install_fable_plume53.py','installer53')

# A minimal fixture containing the exact Plume46 C++ anchors, not game code.
HEADER = '''bool unrelated() { return true; }
  bool Initialize(plume::RenderDevice* device);
  std::unique_ptr<plume::RenderBuffer> fable_loop_constants_;
  void* fable_loop_constants_mapped_ = nullptr;
'''
DRAW = '''#include "fable_loop_constants_46.h"
  fable_loop_constants_mapped_ = nullptr;
  fable_loop_constants_.reset();
  draw_set_builder_.addConstantBufferDynamic(7);
  fable_loop_constants_ = make_cb(uint64_t(kFableLoopSlotBytes) * kCbSlots, "Fable Xenos loop constants");
    made.set->setBuffer(3 + 4 * kDrawSlots, fable_loop_constants_.get(), kFableLoopConstantBytes);
PlumeDrawContext::~PlumeDrawContext() {
}
'''
GRAPHICS = '''  swapchain_->ClearAndPresent(0.03f, 0.04f, 0.07f, 1.0f, encode, &ctx, resolve, hold);
'''

class OverlayTests(unittest.TestCase):
    def test_real_storage_bindings(self):
        actual=patch.patch_draw(DRAW)
        self.assertIn('addReadWriteByteAddressBuffer(8)',actual)
        self.assertIn('addReadWriteByteAddressBuffer(9)',actual)
        self.assertIn('RenderBufferDesc::ReadbackBuffer',actual)
        self.assertIn('vertexPipelineStoresAndAtomics',actual)
        self.assertIn('vkGetPhysicalDeviceFeatures',actual)
        self.assertIn('FinishMemExport52',actual)
        self.assertIn('kStatsDescriptorIndex',actual)
        self.assertIn('guest commit DISABLED',actual)
        self.assertNotIn('TranslatePhysical',actual)

    def test_headers_and_fence_integration(self):
        self.assertIn('memexport52_memory_',patch.patch_header(HEADER))
        self.assertIn('memexport52_stats_',patch.patch_header(HEADER))
        actual=patch.patch_graphics(GRAPHICS)
        self.assertLess(actual.index('BeginMemExport52'),actual.index('swapchain_->ClearAndPresent'))
        self.assertGreater(actual.index('FinishMemExport52'),actual.index('swapchain_->ClearAndPresent'))

    def test_duplicate_or_drifted_anchor(self):
        with self.assertRaises(ValueError):patch.patch_draw(DRAW+DRAW)
        with self.assertRaises(ValueError):patch.patch_graphics('old renderer layout')
        with self.assertRaises(ValueError):patch.patch_header(HEADER+HEADER)

    def test_manifest_idempotence_and_no_upstream_modifications(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            upstream=base/'Xerenge'; upstream.mkdir()
            overlay46=base/'build46'; overlay46.mkdir()
            (overlay46/'plume_draw.cpp').write_text(DRAW)
            (overlay46/'plume_graphics_system.cpp').write_text(GRAPHICS)
            (overlay46/'plume_renderer').mkdir()
            (overlay46/'plume_renderer/plume_draw.h').write_text(HEADER)
            overlay52=base/'build52'
            patch.prepare(upstream,overlay46,overlay52)
            self.assertTrue((overlay52/'plume52-manifest.json').exists())
            patch.prepare(upstream,overlay46,overlay52)
            self.assertEqual(list(upstream.iterdir()),[])
            (overlay52/'plume_draw.cpp').write_text('tampered')
            with self.assertRaises(ValueError):patch.prepare(upstream,overlay46,overlay52)

    def test_installer_once_and_check(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'scripts').mkdir()
            build=root/'scripts/build_fable_gpu.sh'
            build.write_text('start\n'+installer.BEFORE+'\nend\n')
            with self.assertRaises(ValueError):installer.run(root,True)
            installer.run(root,False)
            installer.run(root,True)
            installer.run(root,False)
            self.assertEqual(build.read_text().count(installer.MARK),1)
            self.assertIn('apply_fable_plume52.py',build.read_text())

    def test_installed_53_preserves_verified_52_without_mutation(self):
        # The exact 53 extension is inverted in memory, never on disk.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'scripts').mkdir()
            build=root/'scripts/build_fable_gpu.sh'
            build.write_text('start\n'+installer.BEFORE+'\nend\n')
            installer.run(root,False)
            installer53.run(root,False)
            installed=build.read_bytes()
            installer.run(root,True)
            installer.run(root,False)
            self.assertEqual(build.read_bytes(),installed)
            self.assertEqual(build.read_text().count(installer53.MARK),1)
            self.assertIn(installer53.AFTER,build.read_text())

    def test_installed_53_tamper_rejected_by_52_check(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'scripts').mkdir()
            build=root/'scripts/build_fable_gpu.sh'
            build.write_text(installer.BEFORE)
            installer.run(root,False)
            installer53.run(root,False)
            good=build.read_text()
            # Both a damaged downstream 53 and a damaged ancestor 52 fail closed.
            tampered53=good.replace('apply_fable_plume53.py','apply_fable_plume53_missing.py',1)
            build.write_text(tampered53)
            with self.assertRaisesRegex(ValueError,'Plume53 integration'):
                installer.run(root,True)
            tampered52=good.replace('plume46_overlay="$root/build/fable2-plume-overlay-46"',
                                    'plume46_overlay="$root/build/unexpected"',1)
            build.write_text(tampered52)
            with self.assertRaisesRegex(ValueError,'Plume52 installed'):
                installer.run(root,True)
            build.write_text(good)
            installer.run(root,True)

    def test_fail_if_overlay_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            with self.assertRaises(ValueError):patch.prepare(base,base/'missing46',base/'overlay52')

if __name__=='__main__':unittest.main()
