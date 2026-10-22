import tempfile
import unittest
from pathlib import Path
from scripts.compare_sdk_abi import HEADERS, compare, abi_version


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
