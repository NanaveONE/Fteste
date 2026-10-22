import tempfile
import unittest
from pathlib import Path
from scripts.compare_sdk_abi import HEADERS, compare, abi_version, virtual_layout


class SDKAbiChecks(unittest.TestCase):
    def test_abi_number_parser(self):
        self.assertEqual(abi_version('inline constexpr uint32_t kGpuPluginAbiVersion = 1;'), '1')
        self.assertIsNone(abi_version('nothing declared'))

    def test_matching_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/'a', Path(temp)/'b'
            for root in (a,b):
                for header in HEADERS:
                    p = root/header
                    p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_text('inline constexpr uint32_t kGpuPluginAbiVersion = 1;')
            failures, warnings = compare(a,b)
            self.assertFalse(failures)
            self.assertFalse(warnings)

    def test_graphics_vtable_mismatch_blocks_even_with_equal_plugin_version(self):
        # Xerenge has extra virtual methods absent from Fable II's SDK.
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'a', Path(temp) / 'b'
            for root in (a, b):
                for header in HEADERS:
                    file = root / header
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text('inline constexpr uint32_t kGpuPluginAbiVersion = 1;')
            (a / HEADERS[1]).write_text("class GPU { public: virtual void Setup() = 0; virtual void Shutdown() = 0; };")
            (b / HEADERS[1]).write_text("class GPU { public: virtual void Setup() = 0; virtual void Present() {} virtual void Shutdown() = 0; };")
            errors, warnings = compare(a, b)
            self.assertTrue(any('Different IGraphicsSystem' in e for e in errors), errors)
            self.assertTrue(warnings)

    def test_virtual_layout_ignores_comments(self):
        a = '/* virtual void Bogus() = 0; */ virtual void Real(int a) = 0;'
        self.assertEqual(virtual_layout(a), ['void Real(int a) = 0'])

    def test_version_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/'a', Path(temp)/'b'
            for root, v in ((a, '1'), (b, '2')):
                for header in HEADERS:
                    p=root/header
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('inline constexpr uint32_t kGpuPluginAbiVersion = ' + v + ';')
            failures, warnings=compare(a,b)
            self.assertTrue(any('Incompatible GPU ABI' in s for s in failures))
            self.assertTrue(warnings)


if __name__ == '__main__':
    unittest.main()
