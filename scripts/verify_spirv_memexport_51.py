#!/usr/bin/env python3
"""Fail-closed private experimental SPIR-V static validation, no game contents."""
from __future__ import annotations
import argparse, json, struct, zipfile
from pathlib import Path
from collections import defaultdict, Counter

def inspect(blob:bytes)->dict:
    if len(blob)<20 or len(blob)%4 or blob[:4]!=b'\x03\x02\x23\x07':
        raise ValueError('Invalid SPIR-V header or truncated words')
    words=struct.unpack('<'+str(len(blob)//4)+'I',blob)
    i=5;capabilities=[]; decorations=defaultdict(dict);opcodes=Counter()
    while i<len(words):
        instr=words[i]; length=instr>>16; opcode=instr&65535
        if length==0 or i+length>len(words):
            raise ValueError('Malformed SPIR-V instruction length')
        opcodes[opcode]+=1
        if opcode==17 and length>=2:capabilities.append(words[i+1])
        if opcode==71 and length>=4:
            target, decoration, data=words[i+1:i+4]
            if decoration in (33,34):decorations[target][decoration]=data
        i+=length
    bindings={(d[34],d[33]) for d in decorations.values() if 34 in d and 33 in d}
    if (0,8) not in bindings or (0,9) not in bindings:
        raise ValueError('Missing memory binding8 or diagnostic binding9')
    if 11 in capabilities:
        raise ValueError('ShaderInt64 required: not portable across Android devices')
    # SPIR-V OpAtomicIAdd = 234; OpStore = 62; both expected for real
    # buffer side effects, though their presence alone cannot prove semantics.
    if opcodes[234]<1 or opcodes[62]<1:
        raise ValueError('GPU side-effects not found in shader')
    return {'bytes':len(blob),'bindings':sorted(list(bindings)),
            'has_shader_int64':False,'atomic_add_instructions':opcodes[234],
            'store_instructions':opcodes[62]}

def inspect_zip(path:Path)->dict:
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('report.json'))
        shaders=manifest.get('shaders',[])
        if len(shaders)!=5 or len({x['hash'] for x in shaders})!=5:
            raise ValueError('Expected five distinct experimental Fable shaders')
        result={}
        for entry in shaders:
            name='private-spirv/'+entry['hash'].lower()+'.spv'
            result[entry['hash']]=inspect(z.read(name))
        return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_zip',type=Path)
    a=p.parse_args()
    try:
        result=inspect_zip(a.private_zip)
    except (KeyError,ValueError,OSError,zipfile.BadZipFile) as e:p.exit(2,f'BLOCKED: {e}\n')
    print('PASS: five experimental SPIR-V modules with writes and bindings 8/9; no Int64')
    for key,info in result.items():
        print(key,info['bytes'],'bytes',info['bindings'])
    print('DOES NOT validate guest-memory semantics or Vulkan runtime availability.')

if __name__=='__main__': main()
