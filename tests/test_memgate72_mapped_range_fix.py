"""Regression for the real 260-character SDK AddVirtualMappedRange header.

No game inputs or private libraries are required. The signature below matches
ReXGlue pin 3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b.
"""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/patch_rex_memgate72_sdk.py'
spec = importlib.util.spec_from_file_location('memgate72_real_header', SCRIPT)
sdk72 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk72)

REAL_MAPPED = (
    'bool Memory::AddVirtualMappedRange(uint32_t virtual_address, uint32_t mask, uint32_t size,\n'
    '                                   void* context, runtime::MMIOReadCallback read_callback,\n'
    '                                   runtime::MMIOWriteCallback write_callback) {\n'
)


def sdk_fixture():
    # Use the complete real header + the two independent heap handlers.
    return ('#include <rex/system/xmemory.h>\n' + ''.join(
        sig + '  return {};\n}\n' for sig, _kind, _label in sdk72.MEMORY_FUNCTIONS
    ))


class PinnedMemoryHeaderTests(unittest.TestCase):
    def test_exact_long_pinned_signature(self):
        self.assertEqual(sdk72.MEMORY_FUNCTIONS[0][0], REAL_MAPPED)
        self.assertEqual(REAL_MAPPED.index('{\n'), 260)
        self.assertTrue(all(sig.endswith(' {\n') for sig, _, _ in
                            sdk72.COMMAND_FUNCTIONS + sdk72.MEMORY_FUNCTIONS + sdk72.SHARED_FUNCTIONS))

    def test_real_multiline_header_rewrite_and_reverse_verification(self):
        base = sdk_fixture()
        name = sdk72.FILES[1]
        after = sdk72.modify(name, base)
        self.assertEqual(after.count('FABLE2_MEMGATE72_RUNTIME_HOOK'), 1)
        self.assertEqual(after.count('fable72_mapped_range'), 1)
        self.assertIn(REAL_MAPPED + sdk72._guard('FABLE_M71_DMA_MAPPING', 'mapped_range'), after)
        sdk72._validate_installed(name, after)
        for _sig, _kind, label in sdk72.MEMORY_FUNCTIONS:
            self.assertEqual(after.count('fable72_'+label), 1)
        with self.assertRaises(ValueError):
            sdk72.modify(name, after)

    def test_reverse_rejects_removed_or_moved_guard(self):
        name = sdk72.FILES[1]
        correct = sdk72.modify(name, sdk_fixture())
        guard = sdk72._guard('FABLE_M71_DMA_MAPPING', 'mapped_range')
        for bad in (correct.replace(guard, '', 1),
                    correct.replace(REAL_MAPPED+guard, guard+REAL_MAPPED, 1),
                    correct.replace('fable72_mapped_range', 'unregistered_writer', 1)):
            with self.subTest(bad=bad[:60]), self.assertRaises(ValueError):
                sdk72._validate_installed(name, bad)

    def test_wrong_or_duplicated_signature_is_rejected(self):
        name = sdk72.FILES[1]
        base = sdk_fixture()
        examples = (base.replace('runtime::MMIOWriteCallback write_callback) {',
                                 'runtime::MMIOWriteCallback write_callback) const {', 1),
                    base.replace('void* context,', 'void* changed_context,', 1),
                    base + REAL_MAPPED + '  return false;\n}\n')
        for bad in examples:
            with self.subTest(bad=bad.count('AddVirtualMappedRange')):
                with self.assertRaises(ValueError):
                    sdk72.modify(name, bad)

    def test_other_function_headers_unchanged(self):
        sig, kind, label = sdk72.SHARED_FUNCTIONS[0]
        original = '#include <rex/graphics/shared_memory.h>\n' + sig + '  return;\n}\n'
        installed = sdk72.modify(sdk72.FILES[2], original)
        sdk72._validate_installed(sdk72.FILES[2], installed)
        self.assertIn(sdk72._guard(kind, label), installed)

    def test_pinned_three_memory_sites_remain_diagnostic_only(self):
        content = sdk72.modify(sdk72.FILES[1], sdk_fixture())
        self.assertEqual(len(sdk72.MEMORY_FUNCTIONS), 3)
        self.assertIn('FABLE_M71_DMA_MAPPING', content)
        self.assertNotIn('commit_permitted = True', content)
        self.assertNotIn('memexport_commit_permitted = True', content)


    def test_rexglue_three_sources_installed_checked_and_pinned(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch as mock_patch
        with TemporaryDirectory() as td:
            sdk = Path(td)
            for fname in sdk72.FILES:
                target = sdk / fname
                target.parent.mkdir(parents=True, exist_ok=True)
                if fname == sdk72.FILES[0]:
                    data = ('#include <rex/graphics/command_processor.h>\n'
                            + ''.join('void f(){\n  ' + s + '\n}\n'
                                      for s, _, _ in sdk72.COMMAND)
                            + ''.join(s + '  return true;\n}\n'
                                      for s, _, _ in sdk72.COMMAND_FUNCTIONS))
                elif fname == sdk72.FILES[1]:
                    data = sdk_fixture() + '// FABLE2_MEMGATE71_COOPERATIVE_SCOPE\n'
                else:
                    data = '#include <rex/graphics/shared_memory.h>\n' + ''.join(
                        s + '  return;\n}\n' for s, _, _ in sdk72.SHARED_FUNCTIONS)
                target.write_text(data)
            (sdk/'CMakeLists.txt').write_text('FABLE2_MEMGATE71_SHARED_RUNTIME\n')
            with mock_patch.object(sdk72.subprocess, 'check_output', return_value=sdk72.PIN+'\n'):
                stats = sdk72.patch(sdk)
                self.assertEqual(stats['source_files'], 3)
                self.assertFalse(stats['commit_permitted'])
                verified = sdk72.patch(sdk, check=True)
                self.assertEqual(stats['scope_sites'], verified['scope_sites'])
                with self.assertRaises(ValueError):
                    sdk72.patch(sdk)
                body = sdk / sdk72.FILES[1]
                body.write_text(body.read_text().replace('fable72_mapped_range',
                                                          'unregistered_writer', 1))
                with self.assertRaises(ValueError):
                    sdk72.patch(sdk, check=True)

    def test_source_drift_aborts_before_any_rewrite(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch as mock_patch
        with TemporaryDirectory() as td:
            sdk = Path(td)
            paths = {}
            for fname in sdk72.FILES:
                target = sdk / fname
                target.parent.mkdir(parents=True, exist_ok=True)
                if fname == sdk72.FILES[0]:
                    data = ('#include <rex/graphics/command_processor.h>\n'
                            + ''.join('void f(){\n  ' + s + '\n}\n'
                                      for s, _, _ in sdk72.COMMAND)
                            + ''.join(s + '  return true;\n}\n'
                                      for s, _, _ in sdk72.COMMAND_FUNCTIONS))
                elif fname == sdk72.FILES[1]:
                    data = (sdk_fixture()
                            .replace('runtime::MMIOWriteCallback write_callback) {',
                                     'runtime::MMIOWriteCallback write_callback) const {')
                            + '// FABLE2_MEMGATE71_COOPERATIVE_SCOPE\n')
                else:
                    data = '#include <rex/graphics/shared_memory.h>\n' + ''.join(
                        s + '  return;\n}\n' for s, _, _ in sdk72.SHARED_FUNCTIONS)
                target.write_text(data)
                paths[target] = data
            (sdk/'CMakeLists.txt').write_text('FABLE2_MEMGATE71_SHARED_RUNTIME\n')
            with mock_patch.object(sdk72.subprocess, 'check_output', return_value=sdk72.PIN+'\n'):
                with self.assertRaises(ValueError):
                    sdk72.patch(sdk)
            for path, original in paths.items():
                self.assertEqual(path.read_text(), original)

if __name__ == '__main__':
    unittest.main()
