"""Prevent the obsolete Android SDK `tools` package breaking workflow_dispatch.

Pure stdlib test: CI does not need PyYAML or the Android SDK to run this.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build-android-runtime.yml'


class AndroidRuntimeSetupTests(unittest.TestCase):
    def test_setup_android_explicitly_avoids_legacy_tools_package(self):
        contents = WORKFLOW.read_text(encoding='utf-8')
        action = re.search(
            r'(?m)^\s+-\s+name:\s+Preparar Android SDK.*?'
            r'\n\s+uses:\s+android-actions/setup-android@v3'
            r'\n\s+with:\s*\n(?P<with>(?:\s{10,}[^\n]*\n)+)',
            contents,
        )
        self.assertIsNotNone(action, 'Android setup must declare its package inputs explicitly')
        spec = action.group('with')
        packages = re.search(r'(?m)^\s+packages:\s*(\S.*?)\s*$', spec)
        self.assertIsNotNone(packages)
        tokens = packages.group(1).split()
        self.assertIn('platform-tools', tokens)
        self.assertNotIn('tools', tokens, 'Legacy SDK tools package was removed')

    def test_ndk_version_path_matches_installed_package(self):
        contents = WORKFLOW.read_text(encoding='utf-8')
        versions = re.findall(r'ndk[;/](\d+\.\d+\.\d+)', contents)
        self.assertEqual(versions, ['27.2.12479018', '27.2.12479018'])
        self.assertIn('bash scripts/build_rexglue_android_sdk.sh', contents)
        self.assertIn('librexruntime.so', contents)


if __name__ == '__main__':
    unittest.main()
