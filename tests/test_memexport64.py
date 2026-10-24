import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from classify_memexport64_guest_access import classify

class ClassifierTests(unittest.TestCase):
    def test_conservative(self):
        result = classify([('fable_2_recomp.0.cpp', b'auto x = reinterpret_cast<int*>(p); *reinterpret_cast<int*>(p) = 3;')])
        self.assertEqual(result['translation_units'], 1)
        self.assertFalse(result['memexport_commit_permitted'])
        self.assertEqual(result['heuristic_counts']['cast_occurrences'], 2)
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            classify([])
    def test_no_private_content_in_report(self):
        result = classify([('fable_2_recomp.0.cpp', b'secret_marker reinterpret_cast<int*>(p);')])
        self.assertNotIn('secret_marker', str(result))
    def test_not_certified_with_zero_hits(self):
        result = classify([('fable_2_recomp.0.cpp', b'int main() {return 0;}')])
        self.assertFalse(result['global_exclusion_certified'])
