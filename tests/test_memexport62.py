"""Source-only exact-anchor tests. No Fable II game files."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch62', ROOT/'scripts/patch_rex_memexport62.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

THREAD = '#include <rex/system/xthread.h>\nvoid XThread::Execute() {\n  ExecuteReal();\n}\n'
MEMORY = ('#include <rex/system/xmemory.h>\n'
          'void Memory::Zero(uint32_t address, uint32_t size) {\n  RealZero();\n}\n'
          'void Memory::Fill(uint32_t address, uint32_t size, uint8_t value) {\n  RealFill();\n}\n'
          'void Memory::Copy(uint32_t dest, uint32_t src, uint32_t size) {\n  RealCopy();\n}\n')

class MemExport62Tests(unittest.TestCase):
    def test_guest_entry_scoped(self):
        result = module.transform('src/system/xthread.cpp', THREAD)
        self.assertEqual(result.count(module.MARK), 1)
        self.assertIn('WriterPath::GuestExecute', result)
        self.assertIn('ExecuteReal();', result)

    def test_actual_sdk_memory_helpers(self):
        result = module.transform('src/system/xmemory.cpp', MEMORY)
        for name in ['MemoryZero', 'MemoryFill', 'MemoryCopy']:
            self.assertIn('WriterPath::' + name, result)
        self.assertEqual(result.count(module.MARK), 3)
        self.assertIn('RealCopy();', result)

    def test_reject_changed_source_or_duplicate(self):
        for name, source in [('src/system/xthread.cpp', THREAD),
                             ('src/system/xmemory.cpp', MEMORY)]:
            with self.assertRaises(ValueError): module.transform(name, source + source)
            modified = module.transform(name, source)
            with self.assertRaises(ValueError): module.transform(name, modified)
            with self.assertRaises(ValueError): module.transform(name, 'changed pinned sdk')

    def test_pinned_sdk_application_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = root/'sdk'
            for p, data in [('src/system/xthread.cpp', THREAD),
                            ('src/system/xmemory.cpp', MEMORY)]:
                f = sdk/p
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(data)
            header = root/'port/sdk/fable_memexport_sdk62.h'
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_bytes((ROOT/'port/sdk/fable_memexport_sdk62.h').read_bytes())
            def fake_git(args, *, text):
                if args[-2:] == ['rev-parse', 'HEAD']: return module.PIN + '\n'
                if args[-1] == 'HEAD:src/system/xthread.cpp': return THREAD
                if args[-1] == 'HEAD:src/system/xmemory.cpp': return MEMORY
                raise AssertionError(args)
            with patch.object(module.subprocess, 'check_output', side_effect=fake_git):
                with self.assertRaisesRegex(ValueError, 'not yet installed'):
                    module.patch(sdk, root, True)
                result = module.patch(sdk, root, False)
                self.assertFalse(result['globally_exclusive_verified'])
                module.patch(sdk, root, True)
                module.patch(sdk, root, False)
                (sdk/'src/system/xthread.cpp').write_text('tampered')
                with self.assertRaises(ValueError): module.patch(sdk, root, True)

    def test_scripts_install_before_runtime_build(self):
        src = (ROOT/'scripts/build_rexglue_android_sdk.sh').read_text()
        self.assertIn('patch_rex_memexport62.py', src)
        self.assertLess(src.index('patch_rex_memexport62.py'), src.index('cmake -S "$sdk"'))
        self.assertIn('--check', src)

if __name__ == '__main__':
    unittest.main()
