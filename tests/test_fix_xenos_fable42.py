import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fix_xenos_fable42', ROOT / 'scripts/fix_xenos_fable42.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CPP = '''void test() {
    bool printedRegisters[32]{};
    for (size_t i = 0; i < 32; i++)
    {
        if (!printedRegisters[i])
            print("r{}", i);
    }
    if (shaderContainer->definitionTableOffset != 0)
    {
                println("\\tint4 i{} = int4({}, {}, {}, {});",
                    (definition->registerIndex - 8992) / 4 + i,
                    components.x, components.y, components.z, components.w);
    }
            default:
            {
                auto findResult = interpolators.find(instr.vectorDest);
            }
}
'''
HDR = '[[vk::binding(6, 0)]] SamplerState g_SamplerDescriptorHeap[16];'

class Patch42Test(unittest.TestCase):
    def test_64_registers(self):
        out = mod.patch_recompiler(CPP)
        self.assertIn('bool printedRegisters[64]{};', out)
        self.assertIn('i < 64;', out)
        self.assertNotIn('printedRegisters[32]', out)

    def test_integer_constants_runtime_bound(self):
        out = mod.patch_recompiler(CPP)
        self.assertIn('g_IntegerShaderConstants', out)
        self.assertIn('println("\\ti{} = int4(', out)
        self.assertNotIn('int4 i0 = 0', out)
        self.assertIn('[[vk::binding(7, 0)]]', mod.patch_header(HDR))

    def test_memexport_explicit_block(self):
        out = mod.patch_recompiler(CPP)
        self.assertIn('ExportRegister::ExportAddress', out)
        self.assertIn('FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT', out)

    def test_fail_closed_and_no_partial_writes(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t) / 'XenosRecomp'
            base.mkdir()
            (base / 'shader_recompiler.cpp').write_text(CPP)
            (base / 'shader_common.h').write_text('missing anchor')
            with self.assertRaises(ValueError):
                mod.apply(Path(t), revision_check=False)
            self.assertEqual((base / 'shader_recompiler.cpp').read_text(), CPP)

    def test_idempotence_rejected(self):
        out = mod.patch_recompiler(CPP)
        with self.assertRaises(ValueError):
            mod.patch_recompiler(out)

if __name__ == '__main__':
    unittest.main()
