import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fix_fable2_frame_limiter_35 import patch, REL, OLD_INCLUDE, OLD_CALL

class TestFrameLimiter(unittest.TestCase):
    def test_patch_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / REL
            p.parent.mkdir(parents=True)
            p.write_text(OLD_INCLUDE + '\nvoid SpinPause() {\n' + OLD_CALL + '\n}\n')
            self.assertEqual(patch(Path(td)), 'patched')
            self.assertIn('std::this_thread::sleep_for', p.read_text())
            self.assertEqual(patch(Path(td)), 'already patched')
    def test_reject_changed_source(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / REL
            p.parent.mkdir(parents=True)
            p.write_text('unrelated source')
            with self.assertRaises(ValueError): patch(Path(td))
if __name__ == '__main__': unittest.main()
