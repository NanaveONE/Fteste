import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('plume61',ROOT/'scripts/apply_fable_plume61.py')
patch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

HEADER='''#pragma once
#include "fable_memexport_guest55.h"
  void SetPhysicalMemoryHost55(fable2::memexport55::PhysicalMemoryHost* host);
  fable2::memexport55::PhysicalMemoryHost* memexport55_host_ = nullptr;
'''
DRAW='''void PlumeDrawContext::SetPhysicalMemoryHost55(
    fable2::memexport55::PhysicalMemoryHost* host) {
  memexport55_host_ = host;
}
PlumeDrawContext::~PlumeDrawContext() {
}
'''

class TestMemExport61(unittest.TestCase):
    def test_exact_hooks_and_no_automatic_activation(self):
        h=patch.patch_header(HEADER)
        d=patch.patch_draw(DRAW)
        self.assertIn('InstallCertifiedRexWorld61', h)
        self.assertIn('memexport61_owned_host_', h)
        self.assertIn('IsVerifiedFor', d)
        self.assertNotIn('InstallCertifiedRexWorld61(', d.split('PlumeDrawContext::~')[1])
        self.assertNotIn('SetPhysicalMemoryHost55(host.get());', d.split('PlumeDrawContext::~')[1])
    def test_fail_closed_unknown_and_duplicate(self):
        for fn,data in ((patch.patch_header,HEADER),(patch.patch_draw,DRAW)):
            with self.assertRaises(ValueError):fn(data+data)
            with self.assertRaises(ValueError):fn('changed upstream')
    def test_idempotence_and_no_upstream_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);upstream=root/'Xerenge';upstream.mkdir()
            base=root/'55';base.mkdir();(base/'plume_renderer').mkdir()
            (base/'plume_renderer/plume_draw.h').write_text(HEADER)
            (base/'plume_draw.cpp').write_text(DRAW)
            (base/'plume_graphics_system.cpp').write_text('unchanged\n')
            out=root/'61'
            self.assertEqual(patch.prepare(upstream,base,out)['enables_guest_writes'],False)
            self.assertEqual(patch.prepare(upstream,base,out)['patch'],61)
            self.assertEqual(list(upstream.iterdir()),[])
            self.assertEqual((out/'plume_graphics_system.cpp').read_text(),'unchanged\n')
            (out/'plume_draw.cpp').write_text('modified')
            with self.assertRaises(ValueError):patch.prepare(upstream,base,out)
    def test_build_script_wires_61_after_55(self):
        s=(ROOT/'scripts/build_fable_gpu.sh').read_text()
        self.assertIn('fable2-plume-overlay-55',s)
        self.assertIn('fable2-plume-overlay-61',s)
        self.assertIn('apply_fable_plume61.py',s)
        self.assertLess(s.index('apply_fable_plume55.py'),s.index('apply_fable_plume61.py'))

if __name__=='__main__':unittest.main()
