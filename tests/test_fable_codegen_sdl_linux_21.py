"""Regression checks for the SDL3 X11 Linux-host codegen workflow.

The tests never need the private Fable II ISO or runtime data.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build-fable-codegen-host.yml'


def script_for_step(text: str, name: str) -> str:
    """Read an indented `run: |` block without needing third-party PyYAML."""
    needle = '      - name: ' + name + '\n'
    start = text.find(needle)
    if start == -1:
        raise AssertionError('Missing workflow step: ' + name)
    rest = text[start + len(needle):]
    if not rest.startswith('        run: |\n'):
        raise AssertionError('Missing run block for step: ' + name)
    lines = []
    for line in rest[len('        run: |\n'):].splitlines():
        if line and not line.startswith('          '):
            break
        lines.append(line[10:] if line else '')
    return '\n'.join(lines) + '\n'


class HostSDLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf8')
        cls.install = script_for_step(cls.text, 'Instalar compilador e dependencias publicas SDL3/X11')
        cls.build = script_for_step(cls.text, 'Compilar gerador de codigo PPC para host Linux x86_64')

    def test_missing_xscrnsaver_dependency_is_installed(self):
        self.assertRegex(self.install, r'\blibxss-dev\b')
        self.assertIn('scrnsaver.h', self.install)
        self.assertNotIn('SDL_X11_XSCRNSAVER=OFF', self.build)

    def test_upcoming_sdl_extensions_are_installed(self):
        for package in ('libxtst-dev', 'libxfixes-dev', 'libxrender-dev',
                        'libxdamage-dev', 'libx11-xcb-dev', 'libxcb-xfixes0-dev'):
            with self.subTest(package=package):
                self.assertRegex(self.install, r'\b' + re.escape(package) + r'\b')
        self.assertIn('XTest.h', self.install)

    def test_linux_backend_pkgconfig_and_git_submodules(self):
        for module in ('x11-xcb', 'wayland-client', 'xkbcommon'):
            self.assertIn(module, self.install)
        self.assertIn('submodule update --init --recursive', self.install)
        self.assertIn('shipa-2/rexglue-xerenge', self.install)

    def test_shell_blocks_have_valid_syntax(self):
        for script in (self.install, self.build):
            result = subprocess.run(['bash', '-n'], input=script, text=True,
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_host_codegen_and_upload_still_present(self):
        self.assertIn('--target rexglue --parallel 2', self.build)
        self.assertIn('--config Release', self.build)
        self.assertIn('scripts/package_fable_codegen_host.py', self.text)
        self.assertIn('codegen --help', self.text)
        self.assertIn('fable2-rexglue-codegen-linux-x86_64', self.text)
        self.assertIn('if-no-files-found: error', self.text)

    def test_does_not_include_or_upload_game_files(self):
        pre_upload = self.text.split('      - name: Publicar gerador')[0]
        self.assertNotIn('default.xex', pre_upload)
        self.assertNotIn('FABLE2_GAME_ROOT', self.text)
        self.assertNotIn('Shaders.sbk', pre_upload)


if __name__ == '__main__':
    unittest.main()
