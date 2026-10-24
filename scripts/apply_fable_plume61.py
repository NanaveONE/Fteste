#!/usr/bin/env python3
"""Overlay61: expose a *certified-only* ReXGlue physical host to Plume55.

No stock ReXGlue process is certified to install it. In particular this
patch NEVER invents a guest-world coordinator or marks missing shaders done.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

MARK = 'FABLE2_PLUME_61_CERTIFIED_GATE'


def one(data: str, old: str, new: str, label: str) -> str:
    count = data.count(old)
    if count != 1:
        raise ValueError(f'{label}: expected one exact anchor, found {count}')
    return data.replace(old, new, 1)


def patch_header(data: str) -> str:
    data = one(data, '#include "fable_memexport_guest55.h"',
               '#include "fable_memexport_guest55.h"\n#include "fable_memexport_world61.h"\n'
               '// FABLE2_PLUME_61_CERTIFIED_GATE', '61 include')
    data = one(data,
        '  void SetPhysicalMemoryHost55(fable2::memexport55::PhysicalMemoryHost* host);',
        '  void SetPhysicalMemoryHost55(fable2::memexport55::PhysicalMemoryHost* host);\n'
        '  bool InstallCertifiedRexWorld61(\n'
        '      rex::memory::Memory* memory,\n'
        '      fable2::memexport60::CertifiedGuestWorld* certified_world);',
        'public runtime adapter installation')
    data = one(data, '  fable2::memexport55::PhysicalMemoryHost* memexport55_host_ = nullptr;',
        '  fable2::memexport55::PhysicalMemoryHost* memexport55_host_ = nullptr;\n'
        '  std::unique_ptr<fable2::memexport60::RexPhysicalMemoryHost> memexport61_owned_host_;',
        'adapter lifetime')
    return data


def patch_draw(data: str) -> str:
    block = '''// FABLE2_PLUME_61_CERTIFIED_GATE: strict opt-in. The currently pinned
// ReXGlue SDK has no proof that ALL guest/host writers are instrumented.
// Stock startup therefore never calls this method. No false 588/588 gate.
bool PlumeDrawContext::InstallCertifiedRexWorld61(
    rex::memory::Memory* memory,
    fable2::memexport60::CertifiedGuestWorld* certified_world) {
  if (!memory || !certified_world || memexport55_host_ || memexport61_owned_host_ ||
      !certified_world->IsVerifiedFor(fable2::memexport60::kPinnedRexSdkRevision)) {
    return false;
  }
  auto host = std::make_unique<fable2::memexport60::RexPhysicalMemoryHost>(
      memory, certified_world);
  SetPhysicalMemoryHost55(host.get());
  memexport61_owned_host_ = std::move(host);
  return true;
}

'''
    return one(data, 'PlumeDrawContext::~PlumeDrawContext() {',
               block + 'PlumeDrawContext::~PlumeDrawContext() {',
               'certified-only runtime installation')


def prepare(xerenge_root: Path, base_overlay: Path, overlay: Path) -> dict:
    root, base, out = (p.resolve() for p in (xerenge_root, base_overlay, overlay))
    if base == out or root == out or root in out.parents:
        raise ValueError('Overlay61 must not overwrite base55 or Xerenge')
    sources = {
        'plume_renderer/plume_draw.h': (patch_header, base/'plume_renderer/plume_draw.h'),
        'plume_draw.cpp': (patch_draw, base/'plume_draw.cpp'),
        'plume_graphics_system.cpp': (lambda s: s, base/'plume_graphics_system.cpp'),
    }
    blobs = {}
    for name, (fn, src) in sources.items():
        if not src.is_file():
            raise ValueError(f'Missing verified overlay55 source: {src}')
        data = src.read_text()
        if MARK in data:
            raise ValueError(f'Duplicate MemExport61 overlay in {name}')
        blobs[name] = fn(data).encode()
    manifest = {'patch':61, 'state':'CERTIFIED_ONLY_DISABLED_ON_STOCK_RUNTIME',
                'enables_guest_writes':False,
                'files':{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()}}
    meta = out/'plume61-manifest.json'
    if out.exists():
        if not meta.is_file() or json.loads(meta.read_text()) != manifest:
            raise ValueError('Existing overlay61 manifest mismatch')
        for name, blob in blobs.items():
            if not (out/name).is_file() or (out/name).read_bytes() != blob:
                raise ValueError(f'Existing overlay61 source changed: {name}')
        return manifest
    out.mkdir(parents=True)
    for name, blob in blobs.items():
        p=out/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    meta.write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xerenge-root', type=Path, required=True)
    p.add_argument('--base-overlay', type=Path, required=True)
    p.add_argument('--overlay', type=Path, required=True)
    a=p.parse_args()
    try:
        prepare(a.xerenge_root, a.base_overlay, a.overlay)
        print('PASS: Plume61 can accept a certified Rex physical-world host')
        print('BLOCKED BY DESIGN: stock SDK lacks coverage proof; MemExport guest commits disabled')
    except (ValueError, OSError, json.JSONDecodeError) as e:
        p.exit(2, f'BLOCKED: {e}\n')

if __name__ == '__main__': main()
