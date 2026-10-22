"""16 KiB ELF page-size regression checks; synthetic binaries only."""
from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from scripts.check_android_16k_alignment import audit, load_alignments
from scripts.enable_android_16k import TARGETS, apply


def make_elf(path: Path, *, align: int = 16384, architecture: int = 183,
             offset: int = 0, virtual: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(256)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', data, 16, 3)  # ET_DYN
    struct.pack_into('<H', data, 18, architecture)
    struct.pack_into('<Q', data, 32, 64)  # e_phoff
    struct.pack_into('<H', data, 54, 56)  # e_phentsize
    struct.pack_into('<H', data, 56, 1)   # e_phnum
    struct.pack_into('<I', data, 64, 1)   # PT_LOAD
    struct.pack_into('<QQ', data, 64 + 8, offset, virtual)
    struct.pack_into('<Q', data, 64 + 48, align)
    path.write_bytes(data)


class ElfTests(unittest.TestCase):
    def test_aligned_arm64_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'librexruntime.so'
            make_elf(path)
            self.assertEqual(load_alignments(path), [16384])
            report = audit([path])
            self.assertEqual(report['state'], 'PASS')
            self.assertEqual(report['libraries'][path.name]['minimum_pt_load_alignment'], 16384)

    def test_four_k_arm64_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_elf(root / 'librexruntime.so', align=4096)
            make_elf(root / 'libc++_shared.so', align=16384)
            result = audit([root / 'librexruntime.so', root / 'libc++_shared.so'])
            self.assertEqual(result['state'], 'BLOCKED')
            self.assertEqual(result['misaligned_libraries'], ['librexruntime.so'])

    def test_rejects_non_arm64_and_invalid_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'libwrong.so'
            make_elf(path, architecture=62)
            with self.assertRaisesRegex(ValueError, 'AArch64'):
                load_alignments(path)
            make_elf(path, align=3000)
            with self.assertRaisesRegex(ValueError, 'p_align'):
                load_alignments(path)
            make_elf(path, offset=4096, virtual=0)
            with self.assertRaisesRegex(ValueError, 'Incongruent'):
                load_alignments(path)

    def test_rejects_missing_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'empty.so'
            path.write_bytes(b'\0' * 12)
            with self.assertRaisesRegex(ValueError, 'truncated'):
                load_alignments(path)
            make_elf(path)
            raw = bytearray(path.read_bytes())
            struct.pack_into('<H', raw, 56, 9000)
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'program-header'):
                load_alignments(path)


class PatchTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        for rel, (old, _new) in TARGETS.items():
            file = root / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('before\n' + old + 'after\n')
        (root / 'scripts/check_android_16k_alignment.py').write_text('# fixture')

    def test_applies_once_and_checks_all_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            result = apply(root)
            self.assertEqual(list(result.values()), ['updated'] * 5)
            self.assertEqual(list(apply(root).values()), ['verified'] * 5)
            self.assertEqual(list(apply(root, check=True).values()), ['verified'] * 5)
            for rel, (_, new) in TARGETS.items():
                self.assertEqual((root / rel).read_text().count(new), 1)

    def test_check_refuses_mismatched_or_missing_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'setting absent'):
                apply(root, check=True)

    def test_unknown_anchor_aborts_without_editing_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            broken = root / 'scripts/build_fable_gpu.sh'
            broken.write_text('new upstream layout!')
            original = {k: (root / k).read_text() for k in TARGETS}
            with self.assertRaisesRegex(ValueError, 'Cannot safely apply'):
                apply(root)
            self.assertEqual(original, {k: (root / k).read_text() for k in TARGETS})

if __name__ == '__main__':
    unittest.main()
