import importlib.util
import tempfile
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,BASE/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
patch=load('scripts/apply_fable_plume55.py','plume55_patch')
install=load('scripts/install_fable_plume55.py','plume55_install')
upgrade=load('scripts/upgrade_fable55_ci.py','plume55_ci')

HEADER='''#pragma once
  void FinishMemExport53();
  bool memexport53_enabled_ = false;
'''
DRAW='''#include "fable_memexport_journal53.h"
  REXLOG_INFO("guest RAM commit DISABLED");
PlumeDrawContext::~PlumeDrawContext() {
}
'''
GRAPHICS='''  if (draw_context_) draw_context_->FinishMemExport53();
'''

class Test55(unittest.TestCase):
    def test_header_and_hooks(self):
        h=patch.patch_header(HEADER)
        self.assertIn('SetPhysicalMemoryHost55',h)
        self.assertIn('memexport55_host_ = nullptr',h)
        d=patch.patch_draw(DRAW)
        self.assertIn('CommitFencedJournal',d)
        self.assertIn('if (!memexport53_enabled_ || !memexport55_host_',d)
        self.assertNotIn('guest RAM commit DISABLED',d)
        self.assertIn('FinishMemExport55',patch.patch_graphics(GRAPHICS))

    def test_reject_duplicate_and_unknown(self):
        with self.assertRaises(ValueError):patch.patch_header(HEADER+HEADER)
        with self.assertRaises(ValueError):patch.patch_draw(DRAW+DRAW)
        with self.assertRaises(ValueError):patch.patch_graphics('changed upstream')

    def test_isolated_overlay_and_idempotence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);up=root/'Xerenge';up.mkdir()
            base=root/'overlay53';base.mkdir()
            (base/'plume_draw.cpp').write_text(DRAW)
            (base/'plume_graphics_system.cpp').write_text(GRAPHICS)
            (base/'plume_renderer').mkdir()
            (base/'plume_renderer/plume_draw.h').write_text(HEADER)
            out=root/'overlay55'
            patch.prepare(up,base,out)
            patch.prepare(up,base,out)
            self.assertEqual(list(up.iterdir()),[])
            (out/'plume_draw.cpp').write_text('tampered')
            with self.assertRaises(ValueError):patch.prepare(up,base,out)

    def test_installer(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'scripts').mkdir()
            gpu=root/'scripts/build_fable_gpu.sh'
            gpu.write_text('hello\n'+install.BEFORE+'\nworld\n')
            with self.assertRaises(ValueError):install.run(root,True)
            install.run(root,False);install.run(root,True)
            self.assertEqual(gpu.read_text().count(install.MARK),1)
            gpu.write_text(gpu.read_text().replace('plume55.py','plumeXXX.py'))
            with self.assertRaises(ValueError):install.run(root,True)

    def test_previous_installer_upgrade(self):
        # Minimal original sections expected from known 52+53 source.
        old52='''        canonical=s
        if 'FABLE2_PLUME_53_BUILDSCRIPT' in s:
            if s.count(mark53)!=1 or s.count(new53)!=1 or old53 in s:
            canonical=s.replace(new53,old53,1)
'''
        old53='''import argparse
from pathlib import Path
    if MARK in s:
        if s.count(MARK)!=1 or AFTER not in s or BEFORE in s:
            raise ValueError('Existing Plume53 build integration is modified')
'''
        result52=upgrade.patch52(old52)
        result53=upgrade.patch53(old53)
        self.assertIn('FABLE2_PLUME_55_DOWNSTREAM_CI_52',result52)
        self.assertIn('FABLE2_PLUME_55_DOWNSTREAM_CI_53',result53)
        self.assertIn('canonical=canonical.replace(new53,old53,1)',result52)
        self.assertIn('canonical=canonical.replace(item55',result53)
        with self.assertRaises(ValueError):upgrade.patch52(result52)

    def test_no_previous_rewrite_on_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'scripts';p.mkdir()
            a=p/'install_fable_plume52.py';b=p/'install_fable_plume53.py'
            a.write_text('unrecognized');b.write_text('unrecognized')
            with self.assertRaises(ValueError):upgrade.run(root,False)
            self.assertEqual(a.read_text(),'unrecognized')
            self.assertEqual(b.read_text(),'unrecognized')

if __name__=='__main__':unittest.main()
