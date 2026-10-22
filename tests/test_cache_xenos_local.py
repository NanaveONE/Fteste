"""Only runs structural validator when a synthetic fixture is supplied manually."""
import unittest
from scripts.validate_xenosrecomp_cache import CacheError, zstd_decode
class CacheValidationTests(unittest.TestCase):
    def test_wrong_size_is_rejected(self):
        with self.assertRaises(CacheError):
            zstd_decode(b'not-zstandard', 32)
    def test_empty_size_is_rejected(self):
        with self.assertRaises(CacheError):
            zstd_decode(b'', 0)
if __name__ == '__main__':
    unittest.main()
