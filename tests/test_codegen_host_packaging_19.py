"""Static and ELF regression tests for the Linux host codegen packaging workflow."""
from pathlib import Path
import tempfile
import unittest

from scripts.package_fable_codegen_host import elf_machine, find_codegen, inspect_ldd

ROOT = Path(__file__).resolve().parents[1]


class Codegen19Tests(unittest.TestCase):
    def test_elf_rejects_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'example'
            path.write_bytes(b'fake codegen, never silently accept a launcher')
            with self.assertRaisesRegex(ValueError, 'not ELF'):
                elf_machine(path)

    def test_elf_reads_x86_64_machine_field(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.elf'
            hdr = bytearray(20)
            hdr[0:6] = b'\x7fELF\x02\x01'
            hdr[18] = 62
            path.write_bytes(hdr)
            self.assertEqual(elf_machine(path), (2, 1, 62))

    def test_finds_only_single_real_host_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            sdk = Path(folder)
            build = sdk / 'out/linux-amd64/Release'
            build.mkdir(parents=True)
            tool = build / 'rexglue'
            tool.write_text('exe')
            tool.chmod(0o755)
            self.assertEqual(find_codegen(sdk), tool)
            another = sdk / 'out/build/linux-amd64/rexglue'
            another.parent.mkdir(parents=True)
            another.write_text('exe')
            another.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                find_codegen(sdk)

    def test_workflow_has_manual_trigger_and_no_game_asset_upload(self):
        text = (ROOT / '.github/workflows/build-fable-codegen-host.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertIn('target rexglue', text)
        self.assertIn('codegen --help', text)
        self.assertIn('package_fable_codegen_host.py', text)
        self.assertIn('if-no-files-found: error', text)
        self.assertNotIn('default.xex', text.split('      - name: Publicar')[0])
        self.assertNotIn('FABLE2_GAME_ROOT', text)

    def test_script_never_reads_game_files(self):
        text = (ROOT / 'scripts/package_fable_codegen_host.py').read_text()
        self.assertNotIn('open("default.xex")', text)
        self.assertNotIn('FABLE2_GAME_ROOT', text)


if __name__ == '__main__':
    unittest.main()
