import unittest
from scripts.gpu_log_report import summarize


class PlumeFableReportTests(unittest.TestCase):
    def test_extracts_real_missing_shader_hashes(self):
        lines = [
            'plume: FABLE2_MISSING_PIPELINE vs=0123456789ABCDEF (miss) ps=F00DF00DF00DF00D (ok)',
            'plume: FABLE2_MISSING_PIPELINE vs=0123456789ABCDEF (ok) ps=0000000000000FAB (miss)',
            'plume: shader coverage - VS 20/31 distinct, PS 22/25 distinct, draws with both 300/450 (66%)',
        ]
        result = summarize(lines)
        self.assertEqual(result['distinct_missing_vertex_shaders'], ['0123456789abcdef'])
        self.assertEqual(result['distinct_missing_pixel_shaders'], ['0000000000000fab'])
        self.assertEqual(result['distinct_skipped_pipeline_pairs'], 2)
        self.assertEqual(result['last_shader_coverage']['draws_observed'], 450)
        self.assertEqual(result['gpu_issue_counts']['missing_shader'], 2)
        self.assertIn('missing_pipeline', result['gpu_issue_counts'])

    def test_no_coverage_is_not_claimed_as_success(self):
        r = summarize(['hello', 'plume: device initialized'])
        self.assertIsNone(r['last_shader_coverage'])
        self.assertEqual(r['distinct_missing_vertex_shaders'], [])


if __name__ == '__main__':
    unittest.main()
