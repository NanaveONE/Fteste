#!/usr/bin/env python3
"""Experimental Fable II MemExport HLSL translation (PRIVATE output only).

Does NOT replace the approved 583-shader production cache. It translates the
five missing vertex shaders to SPIR-V with genuine Vulkan buffer writes for
Xenos ColorFormat 38 (RGBA32_FLOAT), while counting unsupported writes in a
separate diagnostics SSBO. Missing Vulkan bindings 8/9 or other GPU formats
must NOT be interpreted as a working renderer.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, tempfile, zipfile
from pathlib import Path

MARK='#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT'
ASSIGN=re.compile(r'^(\s*)output\.oPos\.xyzw\s*=\s*(.+);\s*$')
ADDRESS=re.compile(r'\bg_ExportAddress(?:\w*)\b')
HLSL_INSERT='struct VertexShaderInput\n{'
HELPER = r'''
#if defined(__spirv__) && defined(XENOS_VERTEX_SHADER)
// Experimental MemExport 51, buffers MUST be bound and synchronized by Plume.
// set=0,binding=8: guest-memory STORAGE | TRANSFER_SRC buffer. This is NOT a
// dummy output interpolator; real shader side effects are issued.
[[vk::binding(8, 0)]] RWByteAddressBuffer g_FableMemExportMemory51;
// set=0,binding=9: 16-byte per-draw counter buffer, initialized to zero.
// 0 unsupported formats, 4 invalid/out-of-range writes, 8 successful writes.
[[vk::binding(9, 0)]] RWByteAddressBuffer g_FableMemExportStats51;
void FableExportCount51(uint byte_offset) {
    uint prev;
    g_FableMemExportStats51.InterlockedAdd(byte_offset, 1u, prev);
}
void FableMemExportStore51(float4 address, uint em_index, float4 value) {
    uint4 a = asuint(address);
    // Xenos eA stream constants are packed IEEE-754 bit patterns, not
    // numerically converted integers. The MAD to Y adds element index.
    bool magic = (a.x >> 30) == 1u &&
        (a.y & 0xFF800000u) == 0x4B000000u &&
        (a.z >> 20) == 0x4B0u &&
        (a.w & 0xFF800000u) == 0x4B000000u;
    uint index = (a.y & 0x7FFFFFu);
    uint count = (a.w & 0x7FFFFFu);
    if (!magic || index >= count || em_index >= 5u || em_index >= count-index) {
        FableExportCount51(4u);
        return;
    }
    uint format = (a.z >> 8) & 63u;
    uint number_format = (a.z >> 16) & 7u;
    uint endianness = a.z & 7u;
    bool red_blue_swap = (a.z & (1u << 19)) != 0u;
    // Only verified linear RGBA32_FLOAT is supported. Never silently write
    // unconverted 8- or 16-bit guest formats or mixed-endian values.
    if (format != 38u || number_format != 7u || endianness != 0u || red_blue_swap) {
        FableExportCount51(0u);
        return;
    }
    uint base = (a.x & 0x3FFFFFFFu) * 4u;
    uint elem = index + em_index;
    // Entirely 32-bit arithmetic: Android GPUs are not required to support
    // shaderInt64. Check multiplication/addition overflow before computing.
    if (elem > (0xFFFFFFFFu - base) / 16u) {
        FableExportCount51(4u);
        return;
    }
    uint guest_address = base + elem * 16u;
    uint size;
    g_FableMemExportMemory51.GetDimensions(size);
    if (size < 16u || guest_address > size - 16u) {
        FableExportCount51(4u);
        return;
    }
    g_FableMemExportMemory51.Store4(guest_address, asuint(value));
    FableExportCount51(8u);
}
#endif
'''

def transform(shader: str, expected_errors: int) -> tuple[str, list[dict]]:
    if shader.count(MARK) != expected_errors or expected_errors < 1:
        raise ValueError('changed shader markers or unexpected count')
    if shader.count(HLSL_INSERT) != 1:
        raise ValueError('Xenos shader template changed')
    if 'g_FableMemExportMemory51' in shader:
        raise ValueError('already patched')
    original_lines = shader.splitlines(keepends=True)
    converted, streams = [], []
    active_address = None
    em = 0
    i = 0
    while i < len(original_lines):
        line = original_lines[i]
        if line.strip() == MARK:
            if i + 1 >= len(original_lines):
                raise ValueError('orphan memexport marker')
            match = ASSIGN.fullmatch(original_lines[i+1].rstrip('\n'))
            if not match:
                raise ValueError('unrecognized next ALU export')
            indent, expression = match.groups()
            if ADDRESS.search(expression):
                active_address = f'fable_ea51_{len(streams)}'
                streams.append({'address': active_address, 'data_writes': 0})
                em = 0
                converted.append(f'{indent}float4 {active_address} = {expression};\n')
            else:
                if active_address is None:
                    raise ValueError('data export before address')
                if em > 4:
                    raise ValueError('sixth eM export is unsupported')
                converted.append(f'{indent}FableMemExportStore51({active_address}, {em}u, {expression});\n')
                streams[-1]['data_writes'] += 1
                em += 1
            i += 2
            continue
        converted.append(line)
        i += 1
    if not all(x['data_writes'] >= 1 for x in streams):
        raise ValueError('address without a data export')
    whole=''.join(converted)
    whole=whole.replace(HLSL_INSERT, HELPER+'\n'+HLSL_INSERT, 1)
    if MARK in whole or 'FableMemExportStore51' not in whole:
        raise ValueError('incomplete transformation')
    return whole, streams

def run(diagnostic:Path, output:Path, dxc:Path, library:Path) -> dict:
    from zipfile import ZipFile, ZIP_DEFLATED
    if output.exists():
        raise ValueError('Output already exists: refusing to overwrite diagnostics')
    if not dxc.is_file() or not library.is_file():
        raise ValueError('DXC compiler or library missing')
    report={'kind':'EXPERIMENTAL_MEMEXPORT_SHADER_SPIRV_NOT_RUNTIME_SAFE', 'feature_requirements':[
        'Vulkan vertexPipelineStoresAndAtomics enabled',
        'set0 binding8 RWByteAddressBuffer storage on actual guest-mirror memory',
        'set0 binding9 RWByteAddressBuffer 16byte zeroed diagnostic counters',
        'device writes and GPU/CPU barriers + completed readback before guest CPU reads',
        'support other Xenos stream formats and endian cases',
        'verified eM index/masks/predication from Xenos ALU bytecode'], 'shaders':[]}
    with ZipFile(diagnostic) as input_zip:
        ref=json.loads(input_zip.read('diagnostic/memexport-43.json'))
        if ref['translated']!=583 or ref['skipped']!=5 or len(ref['shader_failures'])!=5:
            raise ValueError('unexpected original diagnostic')
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            files=[]
            for item in ref['shader_failures']:
                name=item['shader_hash'].lower()
                payload=input_zip.read(f'missing-hlsl/{name}.hlsl')
                if hashlib.sha256(payload).hexdigest()!=item['hlsl_sha256']:
                    raise ValueError('HLSL hash mismatch '+name)
                rewritten,streams=transform(payload.decode(),item['memexport_directives'])
                src=tmp/f'{name}.hlsl'; src.write_text(rewritten)
                spv=tmp/f'{name}.spv'
                p=subprocess.run([str(dxc),str(library),str(src),str(spv)],capture_output=True,text=True)
                if p.returncode !=0 or not spv.is_file() or spv.read_bytes()[:4]!=b'\x03\x02\x23\x07':
                    raise ValueError('DXC failed '+name+': '+p.stderr[:3000])
                files.extend([(src,f'private-hlsl/{name}.hlsl'),(spv,f'private-spirv/{name}.spv')])
                report['shaders'].append({'hash':item['shader_hash'],'streams':streams,'spirv_bytes':spv.stat().st_size})
            with ZipFile(output,'x',ZIP_DEFLATED,allowZip64=True) as z:
                for path,name in files:z.write(path,name)
                z.writestr('report.json',json.dumps(report,indent=2)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostic',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--dxc',required=True,type=Path)
    p.add_argument('--dxcompiler-library',required=True,type=Path)
    a=p.parse_args()
    try:
        report=run(a.diagnostic,a.output,a.dxc,a.dxcompiler_library)
        print('EXPERIMENTAL SPIR-V:',len(report['shaders']),'out of 5; NOT VALIDATED RUNTIME MEMEXPORT')
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:p.exit(2,'BLOCKED: '+str(e)+'\n')
if __name__=='__main__':main()
