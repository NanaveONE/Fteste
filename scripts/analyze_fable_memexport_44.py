#!/usr/bin/env python3
"""Analyse PRIVATE Fable II MemExport diagnostics without publishing game code.

Input: ZIP from the private GPU diagnostic workflow 43. Output: metadata-only
JSON, safe to use as a development status report. This analyzer does NOT
translate shaders, build a Vulkan driver, or implement GPU memory writes.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

LIMIT_BYTES = 2 * 1024 * 1024
ERROR = '#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT'
HLSL_PATH = re.compile(r'^missing-hlsl/([a-f0-9]{16})\.hlsl$')
STREAM_REF = re.compile(r'g_(ExportAddress(?:Position|Normal|TexCoord\d+)?)\b')
CONST_DECL = re.compile(r'#define\s+g_(ExportAddress(?:Position|Normal|TexCoord\d+)?)\s+g_VertexShaderConstants\[(\d+)\]')
STAGE = re.compile(r'\[shader\("vertex"\)\]|\[\[vertex\]\]')


def analyze(path: Path) -> dict:
    if not path.is_file():
        raise ValueError('Diagnostico ZIP nao encontrado')
    with ZipFile(path) as z:
        if len(z.infolist()) > 64 or sum(x.file_size for x in z.infolist()) > 12 * 1024 * 1024:
            raise ValueError('ZIP excede limites de leitura segura')
        names = set(z.namelist())
        if 'diagnostic/memexport-43.json' not in names:
            raise ValueError('Arquivo memexport-43.json ausente')
        original = json.loads(z.read('diagnostic/memexport-43.json').decode('utf-8'))
        if original.get('total_shaders') != 588 or original.get('translated') != 583 or original.get('skipped') != 5:
            raise ValueError('Numeros inesperados no diagnostico 43')
        failures = original.get('shader_failures')
        if not isinstance(failures, list) or len(failures) != 5:
            raise ValueError('Lista de cinco shaders faltantes invalida')
        shaders = []
        for failure in failures:
            shader_hash = failure.get('shader_hash')
            if not isinstance(shader_hash, str) or not re.fullmatch(r'[A-F0-9]{16}', shader_hash):
                raise ValueError('Identificador de shader invalido')
            filename = f'missing-hlsl/{shader_hash.lower()}.hlsl'
            if filename not in names:
                raise ValueError(f'HLSL ausente: {filename}')
            item = z.getinfo(filename)
            if item.file_size > LIMIT_BYTES:
                raise ValueError('HLSL grande demais')
            source_bytes = z.read(filename)
            if hashlib.sha256(source_bytes).hexdigest() != failure['hlsl_sha256']:
                raise ValueError(f'Hash SHA-256 divergente em {shader_hash}')
            source = source_bytes.decode('utf-8')
            lines = source.splitlines()
            directives = [(i, v) for i, v in enumerate(lines) if v.strip() == ERROR]
            if len(directives) != failure.get('memexport_directives') or not directives:
                raise ValueError(f'Quantidade de MemExport divergente em {shader_hash}')
            if not STAGE.search(source):
                raise ValueError(f'{shader_hash} nao e um vertex shader')
            stream_constants = {name: int(index) for name, index in CONST_DECL.findall(source)}
            if not stream_constants:
                raise ValueError(f'{shader_hash} sem constantes de exportacao')
            streams = []
            last_name = None
            writes = 0
            for i, _ in directives:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if not next_line.startswith('output.oPos'):
                    raise ValueError(f'Marcador alterado/nao reconhecido em {shader_hash}:{i+1}')
                refs = STREAM_REF.findall(next_line)
                if refs:
                    if len(refs) != 1 or refs[0] not in stream_constants:
                        raise ValueError(f'Stream nao mapeado em {shader_hash}:{i+1}')
                    last_name = refs[0]
                    streams.append({'stream': last_name, 'constant_register': stream_constants[last_name], 'data_writes': 0})
                else:
                    if not last_name:
                        raise ValueError(f'Dados de exportacao sem endereco em {shader_hash}:{i+1}')
                    streams[-1]['data_writes'] += 1
                    writes += 1
            shaders.append({
                'hash': shader_hash,
                'stage': 'vertex',
                'memexport_instructions': len(directives),
                'address_writes': len(streams),
                'data_writes': writes,
                'streams': streams,
                'hlsl_sha256_verified': True,
            })
        return {
            'analysis_version': 44,
            'state': 'BLOCKED_GPU_MEMEXPORT',
            'source': 'private diagnostic 43 (HLSL not included in this JSON)',
            'total': 588,
            'compiled': 583,
            'missing': 5,
            'coverage_percent': round(100 * 583 / 588, 2),
            'memexport_instruction_count': sum(s['memexport_instructions'] for s in shaders),
            'memexport_address_writes': sum(s['address_writes'] for s in shaders),
            'memexport_data_writes': sum(s['data_writes'] for s in shaders),
            'shaders': shaders,
            'required_backend_work': [
                'Correct Xenos ALU export destination 32 (eA) and 33..37 (eM0..eM4) masks and predication',
                'Decode xe_gpu_memexport_stream_t address, index, bound, format, endian and component swap',
                'Bind protected GPU storage for guest memory with bounds checks and upload/readback barriers',
                'Use compute-path fallback when vertexPipelineStoresAndAtomics is unavailable',
                'Bind live Xenos integer/loop constant bank at set=0,binding=7 (patch 42)',
                'Implement or validate 1D texture row interpretation and shader/Plume SDK ABI compatibility',
            ],
            'safety': 'Not a renderer or playable APK. Never treat dummy eA/eM writes as complete.'
        }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostic', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    a = p.parse_args()
    try:
        report = analyze(a.diagnostic)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except (ValueError, OSError, UnicodeError, KeyError, json.JSONDecodeError) as e:
        p.exit(2, f'BLOCKED: {e}\n')
    print(f'PASS: {report["missing"]} vertex shaders, {report["memexport_instruction_count"]} MemExport instructions')
    print('OUTPUT:', a.report)
    print('STATUS: genuine MemExport implementation is still required in XenosRecomp and Plume')
    return 0


if __name__ == '__main__':
    sys.exit(main())
