"""Run with: python -m unittest discover -s tests -v (from Fteste root)."""
import unittest
from pathlib import Path
from scripts.fable_shader_1d_compat import RESOURCES, adapt

class ShaderHeaderTests(unittest.TestCase):
    def test_reuses_actual_slot_indices(self):
        src = 'Texture2D<float4> g_Texture2DDescriptorHeap[16];\nfloat4 tfetch2D(uint resourceDescriptorIndex, uint samplerDescriptorIndex, float2 uv, float2 offset) { return 0; }\n'
        result = adapt(src)
        self.assertIn('tfetch2D(resourceDescriptorIndex, samplerDescriptorIndex,', result)
        for resource in RESOURCES:
            self.assertIn(f'#define g_{resource}_Texture1DDescriptorIndex g_{resource}_Texture2DDescriptorIndex', result)
        self.assertEqual(result.count('float4 tfetch1D('), 1)

    def test_fails_when_header_api_changes(self):
        with self.assertRaisesRegex(ValueError, 'Expected'):
            adapt('float4 tfetch2D() {}')

    def test_does_not_modify_upstream_twice(self):
        src = 'Texture2D<float4> g_Texture2DDescriptorHeap[16];\nfloat4 tfetch2D(uint resourceDescriptorIndex, float2 uv) {return 0;}\n'
        with self.assertRaisesRegex(ValueError, 'already'):
            adapt(adapt(src))

if __name__ == '__main__':
    unittest.main()
