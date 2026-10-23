#!/usr/bin/env python3
"""Fable II XenosRecomp translator overlay (experimental, fail-closed).

Patch ONLY an ignored Linux host clone of shipa-2/XenosRecomp-xerenge.
- Cover all 64 Xenos general temporary registers (previously only 32).
- Feed absent integer/loop register values from an explicit Vulkan UBO binding.
  This REQUIRES GPU plugin support for binding 7 before these shaders can run.
- Diagnose memory exports 32..37 explicitly rather than incorrectly relabeling
  them as interpolators. Those exports still require actual GPU implementation.

Passing SPIR-V coverage after further work never demonstrates gameplay.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

PINNED_XENOS = 'a65809bc34cae58bc562c6d6e55198b3bf22ea99'
MARK = 'FABLE2_XENOS_42'


def once(source: str, old: str, new: str, desc: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f'{desc}: expected one exact upstream anchor; got {count}')
    return source.replace(old, new, 1)


def patch_recompiler(source: str) -> str:
    if MARK in source:
        raise ValueError('Source already patched or partial patch present. Use a fresh XenosRecomp clone.')
    source = once(source, '    bool printedRegisters[32]{};',
                  f'    // {MARK}: all 64 guest ALU temporary registers exist.\n'
                  '    bool printedRegisters[64]{};', '64 temporary-register bitset')
    source = once(source, '    for (size_t i = 0; i < 32; i++)\n    {\n        if (!printedRegisters[i])',
                  '    for (size_t i = 0; i < 64; i++)\n    {\n        if (!printedRegisters[i])',
                  '64 temporary-register initialization')
    # On Vulkan SPIR-V, absent integer registers must be supplied by the host,
    # NEVER hardcoded to zero (which silently skips GPU loops).
    source = once(source,
                  '    if (shaderContainer->definitionTableOffset != 0)\n    {',
                  '''    // FABLE2_XENOS_42: Xenos loop/int registers may not be present
    // in the shader's default constant definition table. Read them from
    // explicit runtime-provided integer constants, not fabricated zeroes.
    println("#ifdef __spirv__");
    for (uint32_t n = 0; n < 32; ++n)
        println("\\tint4 i{} = g_IntegerShaderConstants[{}];", n, n);
    println("#endif");

    if (shaderContainer->definitionTableOffset != 0)
    {''', 'explicit dynamic integer constants')
    original_int = '''                println("\\tint4 i{} = int4({}, {}, {}, {});",
                    (definition->registerIndex - 8992) / 4 + i,
                    components.x, components.y, components.z, components.w);'''
    revised_int = '''                // FABLE2_XENOS_42: local defaults override the runtime UBO
                // when present. For other targets, preserve upstream locals.
                println("#ifdef __spirv__");
                println("\\ti{} = int4({}, {}, {}, {});",
                    (definition->registerIndex - 8992) / 4 + i,
                    components.x, components.y, components.z, components.w);
                println("#else");
                println("\\tint4 i{} = int4({}, {}, {}, {});",
                    (definition->registerIndex - 8992) / 4 + i,
                    components.x, components.y, components.z, components.w);
                println("#endif");'''
    source = once(source, original_int, revised_int, 'defined integer register override')
    # A 32..37 VS export is a memory-export address/data register, NOT a
    # VS interpolator. Keep compilation failing until the Vulkan backend
    # supports the memory write semantics; don't silently discard writes.
    anchor = '''            default:
            {
                auto findResult = interpolators.find(instr.vectorDest);'''
    replacement = '''            case ExportRegister::ExportAddress:
            case ExportRegister::ExportData0:
            case ExportRegister::ExportData1:
            case ExportRegister::ExportData2:
            case ExportRegister::ExportData3:
            case ExportRegister::ExportData4:
                // FABLE2_XENOS_42: require an actual GPU memory-export
                // implementation. A dummy TEXCOORD or local discards writes.
                println("#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT");
                exportRegister = "output.oPos"; // HLSL fallback after #error
                break;
            default:
            {
                auto findResult = interpolators.find(instr.vectorDest);'''
    source = once(source, anchor, replacement, 'explicit GPU memexport diagnostic')
    return source


def patch_header(source: str) -> str:
    if MARK in source:
        raise ValueError('Header already modified')
    anchor = '[[vk::binding(6, 0)]] SamplerState g_SamplerDescriptorHeap[16];'
    new = anchor + '''
// FABLE2_XENOS_42: dynamic Xenos integer/loop constant bank.
// GPU plugin MUST bind this UBO at set=0, binding=7 with correct guest data.
[[vk::binding(7, 0)]] cbuffer XenosIntegerConstants
{
    int4 g_IntegerShaderConstants[32];
};'''
    return once(source, anchor, new, 'Vulkan Xenos integer constant binding')


def apply(root: Path, revision_check: bool = True) -> None:
    root = root.resolve()
    base = root / 'XenosRecomp'
    cpp = base / 'shader_recompiler.cpp'
    header = base / 'shader_common.h'
    if not cpp.is_file() or not header.is_file():
        raise ValueError('XenosRecomp source checkout missing')
    if revision_check:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True)
        rev = result.stdout.strip()
        if rev != PINNED_XENOS:
            raise ValueError(f'Wrong XenosRecomp source revision {rev}; expected {PINNED_XENOS}')
    original_cpp = cpp.read_text(encoding='utf-8')
    original_header = header.read_text(encoding='utf-8')
    patched_cpp = patch_recompiler(original_cpp)
    patched_header = patch_header(original_header)
    # Only write after BOTH source anchors pass.
    cpp.write_text(patched_cpp, encoding='utf-8')
    header.write_text(patched_header, encoding='utf-8')
    print('FABLE2_XENOS_42: patched 64 temporary registers and Vulkan integer bank')
    print('BLOCKER: Xenos GPU memory exports still need implementation in Plume')


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xenos', required=True, type=Path, help='Fresh pinned checkout')
    args = p.parse_args()
    try:
        apply(args.xenos)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
