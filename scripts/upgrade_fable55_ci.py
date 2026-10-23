#!/usr/bin/env python3
"""Teach verified old installers to reverse-check a downstream overlay55.

All modifications are exact-anchor, transactional, and confined to public
build verification; missing/altered anchors abort without modifying files.
"""
import argparse
from pathlib import Path

MARK52 = '# FABLE2_PLUME_55_DOWNSTREAM_CI_52'
MARK53 = '# FABLE2_PLUME_55_DOWNSTREAM_CI_53'


def once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected one known anchor, got {text.count(old)}')
    return text.replace(old, new, 1)


def patch52(text):
    if MARK52 in text:
        raise ValueError('52 already patched; use --check')
    old = '''        canonical=s
        if 'FABLE2_PLUME_53_BUILDSCRIPT' in s:'''
    new = '''        # FABLE2_PLUME_55_DOWNSTREAM_CI_52: undo only exact validated
        # downstream scripts IN MEMORY, preserving installed 55 and 53.
        canonical=s
        if 'FABLE2_PLUME_55_BUILDSCRIPT' in canonical:
            layer55=Path(__file__).with_name('install_fable_plume55.py')
            if not layer55.is_file():
                raise ValueError('55 marker found but installer is missing')
            item55=runpy.run_path(str(layer55))
            if canonical.count(item55['MARK'])!=1 or canonical.count(item55['AFTER'])!=1 or item55['BEFORE'] in canonical:
                raise ValueError('55 layer altered, refusing to verify 52')
            canonical=canonical.replace(item55['AFTER'],item55['BEFORE'],1)
        if 'FABLE2_PLUME_53_BUILDSCRIPT' in canonical:'''
    text=once(text,old,new,'52 inserted downstream validation')
    text=once(text,"            if s.count(mark53)!=1 or s.count(new53)!=1 or old53 in s:",
              "            if canonical.count(mark53)!=1 or canonical.count(new53)!=1 or old53 in canonical:",
              '52 downstream check')
    text=once(text,'            canonical=s.replace(new53,old53,1)',
              '            canonical=canonical.replace(new53,old53,1)',
              '52 restore 53')
    return text


def patch53(text):
    if MARK53 in text:
        raise ValueError('53 already patched; use --check')
    text=once(text,'import argparse\nfrom pathlib import Path',
              'import argparse\nimport runpy\nfrom pathlib import Path',
              '53 import')
    original = '''    if MARK in s:
        if s.count(MARK)!=1 or AFTER not in s or BEFORE in s:
            raise ValueError('Existing Plume53 build integration is modified')'''
    replacement = '''    if MARK in s:
        # FABLE2_PLUME_55_DOWNSTREAM_CI_53: check exact 55 then undo in RAM.
        canonical=s
        if 'FABLE2_PLUME_55_BUILDSCRIPT' in canonical:
            layer55=Path(__file__).with_name('install_fable_plume55.py')
            if not layer55.is_file():
                raise ValueError('55 marker found but installer missing')
            item55=runpy.run_path(str(layer55))
            if canonical.count(item55['MARK'])!=1 or canonical.count(item55['AFTER'])!=1 or item55['BEFORE'] in canonical:
                raise ValueError('Downstream 55 is modified or incomplete')
            canonical=canonical.replace(item55['AFTER'],item55['BEFORE'],1)
        if canonical.count(MARK)!=1 or AFTER not in canonical or BEFORE in canonical:
            raise ValueError('Existing Plume53 build integration is modified')'''
    return once(text,original,replacement,'53 downstream validation')


def run(root:Path,check:bool):
    scripts=root/'scripts'
    specs=((scripts/'install_fable_plume52.py',MARK52,patch52),
           (scripts/'install_fable_plume53.py',MARK53,patch53))
    updates={}
    for path,mark,fn in specs:
        if not path.is_file():raise ValueError(f'Missing previous installer {path}')
        orig=path.read_text()
        if mark in orig:
            # Exact safe re-derivation from base is impossible without pinning
            # previous version; check the validated expected behavioral markers.
            if orig.count(mark)!=1 or orig.count('canonical=canonical.replace(item55[\'AFTER\'],item55[\'BEFORE\'],1)')!=1 or (
                (mark==MARK52 and ('canonical=canonical.replace(new53,old53,1)' not in orig or
                                   '55 layer altered, refusing to verify 52' not in orig)) or
                (mark==MARK53 and 'Downstream 55 is modified or incomplete' not in orig)):
                raise ValueError(f'Previously upgraded installer modified: {path}')
            updates[path]=orig
        else:
            if check: raise ValueError(f'Old installer has not been upgraded: {path}')
            updates[path]=fn(orig)
    if not check:
        for path,contents in updates.items():
            path.write_text(contents)
    print('PASS: overlay52 / overlay53 CI understands exact overlay55 chain')

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--root',type=Path,default=Path('.'))
    a.add_argument('--check',action='store_true')
    ns=a.parse_args()
    try:run(ns.root,ns.check)
    except (ValueError,OSError) as exc:a.exit(2,'BLOCKED: '+str(exc)+'\n')
