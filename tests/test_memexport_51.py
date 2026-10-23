import importlib.util
from pathlib import Path
import struct
import unittest

scripts=Path(__file__).resolve().parents[1]/'scripts'
def load(name):
    spec=importlib.util.spec_from_file_location(name,scripts/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
compiler=load('compile_memexport_51')
verifier=load('verify_spirv_memexport_51')

class MemExport51Tests(unittest.TestCase):
    def sample(self):
        return ('struct VertexShaderInput\n{\nfloat4 x;\n};\n'
                'void test(){\n'
                '#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT\n'
                '    output.oPos.xyzw = (float4)(r0.xxxx + g_ExportAddress.xyzw);\n'
                '#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT\n'
                '    output.oPos.xyzw = (float4)(r1.xyzw);\n'
                '}\n')
    def test_real_memexport_not_interpolator(self):
        text, streams=compiler.transform(self.sample(), 2)
        self.assertNotIn(compiler.MARK,text)
        self.assertIn('RWByteAddressBuffer g_FableMemExportMemory51',text)
        self.assertIn('FableMemExportStore51(fable_ea51_0, 0u, (float4)(r1.xyzw));',text)
        self.assertIn('Store4(guest_address, asuint(value));',text)
        self.assertIn('uint elem = index + em_index;',text)
        self.assertIn('elem > (0xFFFFFFFFu - base) / 16u',text)
        self.assertEqual(len(streams),1)
    def test_unexpected_count_rejected(self):
        with self.assertRaises(ValueError):compiler.transform(self.sample(),3)
    def test_data_before_address_rejected(self):
        s=self.sample().replace('r0.xxxx + g_ExportAddress.xyzw','r0.xxxx')
        with self.assertRaises(ValueError):compiler.transform(s,2)
    def test_sixth_export_rejected(self):
        s=self.sample().replace('}\n', ('#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT\n'
            '    output.oPos.xyzw = (float4)(r1.xyzw);\n')*5+'}\n',1)
        with self.assertRaises(ValueError):compiler.transform(s,7)
    def test_no_unsupported_shader_int64(self):
        self.assertNotIn('uint64_t',compiler.HELPER)
        self.assertIn('format != 38u',compiler.HELPER)
        self.assertIn('FableExportCount51(0u)',compiler.HELPER)
    def test_bad_spirv_rejected(self):
        with self.assertRaises(ValueError):verifier.inspect(b'not_spirv')
    def test_descriptors_mandatory(self):
        # SPIR-V header with Shader capability and no decorations.
        words=[0x07230203,0x00010000,0,8,0, (2<<16)|17,1]
        blob=struct.pack('<%dI'%len(words),*words)
        with self.assertRaisesRegex(ValueError,'binding8'):verifier.inspect(blob)

if __name__=='__main__':unittest.main()
