"""Public tests: no files or data derived from Fable II."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts import verify_rex_abi59 as mod


REX_SYMBOL = '_ZN3rex4perf18GetSnapshotCounterENS0_9CounterIdE'
OTHER_SYMBOL = '_ZN3rex10filesystem13GetUserFolderEv'


def line(number, name, defined=True, bind='GLOBAL'):
    ndx = '12' if defined else 'UND'
    return f'    {number}: 0000000000001000    16 FUNC    {bind} DEFAULT  {ndx} {name}'


def symbols(resolves=True):
    return {
        'libfable2.so': ({'SDL_main'}, {REX_SYMBOL, OTHER_SYMBOL}),
        'librexgpu-plume.so': ({'rex_gpu_create', 'rex_gpu_abi_version'}, {OTHER_SYMBOL}),
        'librexruntime.so': ({OTHER_SYMBOL, REX_SYMBOL} if resolves else {OTHER_SYMBOL}, {'puts'}),
        'libc++_shared.so': ({'operator_new'}, {'malloc'}),
    }


def minimal_elf():
    content = bytearray(128)
    content[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HH', content, 16, 3, 183)
    return bytes(content)


def make_private_bundle(path):
    records = {}
    with ZipFile(path, 'w') as z:
        for name in mod.LIBRARIES:
            blob = minimal_elf()
            z.writestr(f'lib/arm64-v8a/{name}', blob)
            records[name] = {'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
        z.writestr('AVISO.txt', 'NAO APK')
        z.writestr('diagnostic/integracao57.json', json.dumps({
            'status': 'PRIVATE_ARM64_NATIVE_INTEGRATION_DIAGNOSTIC_ONLY',
            'production_approved': False, 'apk_generated': False,
            'libraries': records, 'gpu_coverage': {
                'compiled': 583, 'expected': 588, 'missing': 5,
                'missing_hashes': [
                    '17A0FEDEF93DAE25', '1CEC1A730807EC21', '5243696187782727',
                    'AC0C424248A6B1AD', 'DB2ACD9856EB8E28',
                ],
            },
        }))


class ABI59Tests(unittest.TestCase):
    def test_parses_full_symbols_and_ignores_optional_undefined_weak(self):
        source = '\n'.join([
            line(12, REX_SYMBOL, False), line(13, OTHER_SYMBOL),
            line(14, '_ZN3rex4WeakEv', False, 'WEAK'),
        ])
        available, required = mod.parse_dynsym(source)
        self.assertEqual(available, {OTHER_SYMBOL})
        self.assertEqual(required, {REX_SYMBOL})

    def test_rejects_exact_guest_symbol_missing_in_real_private_bundle(self):
        with self.assertRaisesRegex(mod.AbiBlocked, 'GetSnapshotCounter'):
            mod.check_symbols(symbols(False))

    def test_valid_rex_imports_have_proper_coverage(self):
        result = mod.check_symbols(symbols(True))
        self.assertEqual(result['libfable2.so']['rex_resolved_count'], 2)
        self.assertEqual(result['librexgpu-plume.so']['rex_resolved_count'], 1)

    def test_empty_symbol_listing_cannot_pass(self):
        empty = symbols(True)
        empty['libfable2.so'] = ({'SDL_main'}, {'puts'})
        with self.assertRaisesRegex(mod.AbiBlocked, 'no ReXGlue imports'):
            mod.check_symbols(empty)

    def test_zip_integrity_and_dynamic_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'integration-private.zip'
            make_private_bundle(path)
            with patch.object(mod, 'read_dynsym', side_effect=lambda cmd, path: symbols(True)[path.name]):
                result = mod.audit_bundle(path, 'fake-readelf')
            self.assertEqual(result['state'], 'PASS_REX_CPP_IMPORTS_ONLY')
            self.assertIn('not_verified', result)

    def test_build_enables_actual_perf_counter_code(self):
        build = (Path(__file__).resolve().parents[1] / 'scripts/build_rexglue_android_sdk.sh').read_text()
        self.assertIn('-DREXGLUE_ENABLE_PERF_COUNTERS=ON', build)
        self.assertNotIn('-DREXGLUE_ENABLE_PERF_COUNTERS=OFF', build)

    def test_workflow_checks_abi_before_upload(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    '.github/workflows/build-fable2-arm64-integrate57-private.yml').read_text()
        self.assertIn('scripts/verify_rex_abi59.py', workflow)
        self.assertLess(workflow.index('scripts/verify_rex_abi59.py'),
                        workflow.index('gh release upload "$TAG"'))
        self.assertNotIn('actions/upload-artifact', workflow)


if __name__ == '__main__':
    unittest.main()
