#!/usr/bin/env python3
"""Make the Fable II 1D->2D-row *experimental* XenosRecomp include.

The Xerenge Plume backend has 16 indexed Texture2D slots but currently no
Texture1D binding. For *translation testing*, alias Xenos 1D texture slot N to
its existing 2D slot N and sample the middle of a 1-texel-high row.

This removes compiler errors, but it requires the RUNTIME Plume to create a
2D image view with height 1 for those original 1D resources. Do NOT claim
correct gameplay just because DXC compiles it.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

RESOURCES = (
    'BillboardInScattering', 'Extinction', 'GradTexture', 'InScattering',
    'PermTexture', 'ToneMapSampler', 'TreeInScattering',
)
PATCH = '''
// Experimental Fable II shader compatibility. See docs/FABLE2-SPIRV-12.md.
// Runtime requires source 1D textures exposed as width x 1 Texture2D images.
#if defined(__spirv__)
{macros}
float4 tfetch1D(uint resourceDescriptorIndex, uint samplerDescriptorIndex, float coord)
{{
    return tfetch2D(resourceDescriptorIndex, samplerDescriptorIndex,
                    float2(coord, 0.5f), float2(0.0f, 0.0f));
}}
#endif
'''


def adapt(source: str) -> str:
    if 'Fable II shader compatibility' in source or 'float4 tfetch1D(' in source:
        raise ValueError('Original header already has a 1D implementation; review it instead of patching twice')
    if 'float4 tfetch2D(uint resourceDescriptorIndex' not in source:
        raise ValueError('Expected Xerenge 2D sampler implementation not found')
    if 'g_Texture2DDescriptorHeap[16]' not in source:
        raise ValueError('Expected Xerenge 16-slot Texture2D heap not found')
    macros = '\n'.join(f'#define g_{x}_Texture1DDescriptorIndex g_{x}_Texture2DDescriptorIndex'
                       for x in RESOURCES)
    return source + PATCH.format(macros=macros)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--header', type=Path, required=True, help='Unmodified XenosRecomp shader_common.h')
    p.add_argument('--output', type=Path, required=True, help='Private ignored build/ output header')
    a = p.parse_args()
    try:
        if a.output.exists() or a.header.resolve() == a.output.resolve():
            raise ValueError('Refusing overwrite or in-place edit')
        result = adapt(a.header.read_text(encoding='utf-8'))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(result, encoding='utf-8')
    except (OSError, UnicodeError, ValueError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    print('Experimental 1D compatibility header:', a.output)
    print('Original SHA256:', hashlib.sha256(a.header.read_bytes()).hexdigest())
    print('NOTE: requires runtime 1D-as-2D-row support; SPIR-V alone is not gameplay')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
