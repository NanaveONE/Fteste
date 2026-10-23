#!/usr/bin/env python3
"""Upgrade private shader51 HLSL/SPIR-V to fenced export journals (PRIVATE ZIP).

Never writes original/derived game shaders to Fteste. Uses the already-tested
DXC binary, and rejects unexpected shader layout. Does not add shaders to
production cache. 53 is still experimental, requiring real Android validation.
"""
import argparse
import hashlib
import json
import subprocess
import struct
from collections import Counter, defaultdict
import tempfile
import zipfile
from pathlib import Path

MARK = 'FABLE2_MEMEXPORT53_SHADER_JOURNAL'
ORIGINAL = '    g_FableMemExportMemory51.Store4(guest_address, asuint(value));\n    FableExportCount51(8u);'
REPLACEMENT = '''    // FABLE2_MEMEXPORT53_SHADER_JOURNAL: reserve an atomic journal slot.
    uint fable_journal_size;
    g_FableMemExportJournal53.GetDimensions(fable_journal_size);
    uint fable_sequence;
    g_FableMemExportStats51.InterlockedAdd(12u, 1u, fable_sequence);
    if (fable_sequence >= fable_journal_size / 32u) {
        FableExportCount51(4u); // Entire frame must be rejected.
        return;
    }
    uint fable_offset = fable_sequence * 32u;
    uint4 fable_value = asuint(value);
    g_FableMemExportJournal53.Store2(fable_offset, uint2(guest_address, 16u));
    g_FableMemExportJournal53.Store4(fable_offset + 8u, fable_value);
    g_FableMemExportJournal53.Store2(fable_offset + 24u,
                                     uint2(0xF2B1E053u, ~guest_address));
    g_FableMemExportMemory51.Store4(guest_address, fable_value);
    FableExportCount51(8u);'''
DECLARATION = '[[vk::binding(9, 0)]] RWByteAddressBuffer g_FableMemExportStats51;'
NEW_DECL = '''[[vk::binding(9, 0)]] RWByteAddressBuffer g_FableMemExportStats51;
// 32-byte entries, 32K capacity, one journal per synchronous GPU submission.
[[vk::binding(10, 0)]] RWByteAddressBuffer g_FableMemExportJournal53;'''
REQUIRED_HASHES = {'17a0fedef93dae25', '1cec1a730807ec21', '5243696187782727',
                   'ac0c424248a6b1ad', 'db2acd9856eb8e28'}


def transform(hlsl: str) -> str:
    if hlsl.count(ORIGINAL) != 1 or hlsl.count(DECLARATION) != 1 or MARK in hlsl:
        raise ValueError('Shader51 expected MemExport anchors absent, changed or duplicated')
    result = hlsl.replace(DECLARATION, NEW_DECL, 1).replace(ORIGINAL, REPLACEMENT, 1)
    if result.count('[[vk::binding(10, 0)]]') != 1 or result.count(MARK) != 1:
        raise ValueError('Failed to add exact journal shader writes')
    return result


def verify_spirv(blob: bytes) -> dict:
    """Inspect actual compiled SPIR-V, not just HLSL text."""
    if len(blob) < 20 or (len(blob) % 4) or blob[:4] != b'\x03\x02\x23\x07':
        raise ValueError('Invalid SPIR-V header')
    words=struct.unpack('<' + str(len(blob)//4) + 'I',blob)
    decorations=defaultdict(dict)
    opcodes=Counter()
    capabilities=[]
    at=5
    while at < len(words):
        opword=words[at]
        count=opword >> 16
        op=opword & 65535
        if count == 0 or at + count > len(words):
            raise ValueError('Corrupt SPIR-V instructions')
        opcodes[op]+=1
        if op == 17 and count >= 2: capabilities.append(words[at+1])
        if op == 71 and count >= 4 and words[at+2] in (33,34):
            decorations[words[at+1]][words[at+2]]=words[at+3]
        at+=count
    bindings={(d[34],d[33]) for d in decorations.values() if 34 in d and 33 in d}
    if not {(0,8),(0,9),(0,10)}.issubset(bindings):
        raise ValueError('SPIR-V missing required Vulkan bindings 8/9/10')
    if 11 in capabilities:
        raise ValueError('shaderInt64 was required by generated SPIR-V')
    if opcodes[234] < 2 or opcodes[62] < 1:
        raise ValueError('SPIR-V missing atomic journal allocation / storage side effects')
    return {'bindings':sorted(list(bindings)), 'atomic_iadd':opcodes[234],
            'store_instructions':opcodes[62]}


def run(source_zip: Path, output_zip: Path, dxc: Path, library: Path) -> dict:
    if output_zip.exists(): raise ValueError('Refusing to overwrite private output')
    if not dxc.is_file() or not library.is_file(): raise ValueError('DXC inputs absent')
    with zipfile.ZipFile(source_zip) as src, tempfile.TemporaryDirectory() as temp:
        report51 = json.loads(src.read('report.json'))
        hashes = {r['hash'].lower() for r in report51['shaders']}
        if hashes != REQUIRED_HASHES or len(report51['shaders']) != 5:
            raise ValueError('Not the five approved experimental shader51 inputs')
        temp = Path(temp)
        report = {'kind':'PRIVATE_EXPERIMENTAL_MEMEXPORT53_NOT_GUEST_COMMIT',
                  'parent_report_sha256':hashlib.sha256(src.read('report.json')).hexdigest(),
                  'bindings':[8,9,10], 'journal_bytes':1048576,
                  'entry_bytes':32, 'max_entries':32768,
                  'limitations':['Only Xenos linear RGBA32_FLOAT (shader51 path)',
                     'GPU side effects not yet committed to guest physical memory',
                     'Overlapping writes fail host verification',
                     'Guest address encoding still needs live device verification'],
                  'shaders':[]}
        output=[]
        for h in sorted(hashes):
            original = src.read(f'private-hlsl/{h}.hlsl')
            hlsl = transform(original.decode('utf-8'))
            inf = temp / f'{h}.hlsl'; inf.write_text(hlsl)
            outf = temp / f'{h}.spv'
            p = subprocess.run([str(dxc),str(library),str(inf),str(outf)],
                               capture_output=True,text=True)
            if p.returncode or not outf.is_file() or outf.read_bytes()[:4] != b'\x03\x02\x23\x07':
                raise ValueError(f'DXC rejected {h}: {p.stderr[:1500]}')
            parsed_spv = verify_spirv(outf.read_bytes())
            output.extend([(inf,f'private-hlsl/{h}.hlsl'),(outf,f'private-spirv/{h}.spv')])
            report['shaders'].append({'hash':h.upper(),'spv_sha256':hashlib.sha256(outf.read_bytes()).hexdigest(),
                                      'spv_bytes':outf.stat().st_size,'verified_spirv':parsed_spv})
        with zipfile.ZipFile(output_zip, 'x', zipfile.ZIP_DEFLATED) as dest:
            for file,path in output: dest.write(file,path)
            dest.writestr('report.json',json.dumps(report,indent=2)+'\n')
    return report


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--shader51',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True)
    a.add_argument('--dxc',type=Path,required=True)
    a.add_argument('--dxcompiler',type=Path,required=True)
    args=a.parse_args()
    try:
        result=run(args.shader51,args.out,args.dxc,args.dxcompiler)
        print(f'EXPERIMENTAL: {len(result["shaders"])} shaders with binding10 journal, NOT guest commit')
    except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:
        a.exit(2,f'BLOCKED: {e}\n')

if __name__=='__main__':main()
