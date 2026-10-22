"""Synthetic SBK/XenosRecomp layout tests, no game files."""
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from scripts.extract_fable_sbk import MAGIC
from scripts.audit_xenosrecomp_inputs import audit


def bank(*, broken=False):
    v = 60
    container = (struct.pack('>9I', 0x102A1101, v, 12, 0, 36, 0, 36, 0, 0)
                 + struct.pack('>6I', 0, 13 if broken else 12, 0, 0, 0, 0)
                 + b'\0' * 12)
    plain = struct.pack('>5I', 20, 0, 20, 20, 20) + container
    compressor = zlib.compressobj(level=6)
    compressed = compressor.compress(plain) + compressor.flush(zlib.Z_SYNC_FLUSH)
    return MAGIC + b'\0\3\1\0' + b'metadata' + len(compressed).to_bytes(4, 'big') + compressed


class InputAuditTests(unittest.TestCase):
    def test_real_xenosrecomp_shader_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'Shaders.sbk'
            p.write_bytes(bank())
            result = audit([p])
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['containers'], 1)
            self.assertEqual(result['distinct_microcode_sequences'], 1)
            self.assertEqual(result['vertex_shaders'], 1)

    def test_flags_bad_microcode_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'Shaders.sbk'
            p.write_bytes(bank(broken=True))
            result = audit([p])
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(result['problems']['invalid_xenos_microcode_bounds_or_alignment'], 1)

if __name__ == '__main__':
    unittest.main()
