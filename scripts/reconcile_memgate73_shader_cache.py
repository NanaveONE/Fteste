#!/usr/bin/env python3
"""Fail-closed Memgate73 shader-count diagnostic and restricted 43-cache reuse.

Never enables memory-export, never removes a shader from a compressed payload,
and never changes sources outside ignored build/. A fallback is allowed ONLY if
new codegen is a strictly verified subset of historical 583 entries (currently
572, 11 extra translation failures), OR exactly 588 entries consisting of the
original 583 plus the same five MemExport VS. The historical partial cache is
verified against all 588 original SBK inputs before any fallback is allowed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from zipfile import ZipFile, BadZipFile

MISSING = frozenset(int(x, 16) for x in (
    '17A0FEDEF93DAE25', '1CEC1A730807EC21', '5243696187782727',
    'AC0C424248A6B1AD', 'DB2ACD9856EB8E28',
))
ENTRY_TABLE = re.compile(r'ShaderCacheEntry\s+g_shaderCacheEntries\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;', re.S)
ENTRY = re.compile(
    r'\s*\{\s*(0[xX][0-9a-fA-F]+)\s*,\s*\d+\s*,\s*\d+\s*,\s*'
    r'\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*"([^"\n]+)"\s*\},?\s*'
)
FILENAME = re.compile(r'(VS|PS)_([0-9a-f]{64})\.bin', re.I)
MAX_CACHE = 128 * 1024 * 1024

class ReconcileBlocked(ValueError):
    pass

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()

def entries(data: bytes) -> dict[tuple[int,str,str], str]:
    if len(data) > MAX_CACHE:
        raise ReconcileBlocked('Shader C++ cache larger than allowed')
    try:
        source = data.decode('utf-8')
    except UnicodeError as exc:
        raise ReconcileBlocked('Shader cache not valid UTF-8') from exc
    table = ENTRY_TABLE.search(source)
    if table is None:
        raise ReconcileBlocked('Missing shader cache entries table')
    result = {}
    for line in table.group(1).splitlines():
        if not line.strip():
            continue
        match = ENTRY.fullmatch(line)
        if match is None:
            raise ReconcileBlocked('Unrecognized shader entry layout')
        shader_id, path = match.groups()
        name = path.replace('\\', '/').rsplit('/',1)[-1]
        found = FILENAME.fullmatch(name)
        if found is None:
            raise ReconcileBlocked('Shader entry does not carry original source digest')
        stage, digest = found.groups()
        key = (int(shader_id,16), stage.upper(), digest.lower())
        if key in result:
            raise ReconcileBlocked('Duplicate shader identity in cache')
        result[key] = name.casefold()
    if not result:
        raise ReconcileBlocked('Empty shader cache identity table')
    if len(set(result.values())) != len(result):
        raise ReconcileBlocked('Multiple shader hashes map to one input file')
    return result

def verified_inputs(scan: Path, bank_files: list[Path], report: dict) -> set[str]:
    if report.get('source_title') != 'Fable II' or report.get('input_kind') != 'shader_banks' or report.get('extracted_containers') != 588:
        raise ReconcileBlocked('Unknown source or Fable II container count')
    banks = report.get('shader_banks')
    if not isinstance(banks, list) or len(banks) != 2 or len(bank_files) != 2:
        raise ReconcileBlocked('Two source SBKs required')
    listed = {}
    for bank in banks:
        if not isinstance(bank, dict): raise ReconcileBlocked('Invalid source bank record')
        name, digest = str(bank.get('filename','')).lower(), str(bank.get('sha256','')).lower()
        if name in listed or name not in ('shaders.sbk','shadersrelease.sbk') or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ReconcileBlocked('Unexpected shader bank provenance')
        listed[name] = digest
    if len(listed) != 2:
        raise ReconcileBlocked('Missing source SBK bank')
    if {b.name.lower() for b in bank_files} != set(listed):
        raise ReconcileBlocked('Two distinct source bank files required')
    for bank in bank_files:
        if bank.is_symlink() or not bank.is_file() or bank.name.lower() not in listed or file_sha(bank) != listed[bank.name.lower()]:
            raise ReconcileBlocked('SBK input has changed since extraction')
    if not scan.is_dir() or scan.is_symlink():
        raise ReconcileBlocked('Missing or symlinked shader scan directory')
    names = set()
    found = list(scan.glob('*.bin'))
    if len(found) != 588:
        raise ReconcileBlocked(f'Unexpected original input count: {len(found)} (expected 588)')
    for path in found:
        match = FILENAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            raise ReconcileBlocked('Unrecognized or symlinked source shader file')
        # The SBK extractor names every file with SHA256 of original container.
        if file_sha(path) != match.group(2).lower():
            raise ReconcileBlocked('Scan input differs from its original SHA256 name')
        names.add(path.name.lower())
    if len(names) != 588:
        raise ReconcileBlocked('Duplicate guest shader source names')
    return names

def historical(archive: Path) -> tuple[bytes, dict]:
    if not archive.is_file() or archive.is_symlink():
        raise ReconcileBlocked('Missing private diagnostic43 archive')
    try:
        with ZipFile(archive) as z:
            members = z.infolist()
            names = [v.filename for v in members]
            required = ('partial-cache/shader_cache.cpp','diagnostic/memexport-43.json')
            if any(names.count(name) != 1 for name in required):
                raise ReconcileBlocked('Diagnostic43 archive lacks unique required members')
            info = z.getinfo(required[0])
            if info.file_size > MAX_CACHE or info.file_size < 100:
                raise ReconcileBlocked('Historical shader cache size invalid')
            cache = z.read(info)
            diag_info = z.getinfo(required[1])
            if diag_info.file_size > 1_000_000:
                raise ReconcileBlocked('Diagnostic43 JSON too large')
            diag = json.loads(z.read(diag_info))
    except (BadZipFile, OSError, KeyError, json.JSONDecodeError) as exc:
        raise ReconcileBlocked('Invalid private diagnostic43 archive') from exc
    if (diag.get('status') != 'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED' or
        (diag.get('total_shaders'), diag.get('translated'),diag.get('skipped')) != (588,583,5)):
        raise ReconcileBlocked('Unexpected diagnostic43 evidence')
    failure = diag.get('shader_failures', [])
    if (not isinstance(failure, list) or len(failure) != 5 or
        {int(f['shader_hash'],16) for f in failure if isinstance(f,dict) and re.fullmatch('[a-fA-F0-9]{16}',str(f.get('shader_hash','')))} != MISSING or
        any(f.get('hlsl_found') is not True for f in failure)):
        raise ReconcileBlocked('Diagnostic43 failed shader identities mismatch')
    return cache, diag

def check_original_cache(original_path: Path, scan_dir: Path) -> None:
    try:
        from scripts.validate_xenosrecomp_cache import inspect_cpp
    except ModuleNotFoundError:
        from validate_xenosrecomp_cache import inspect_cpp
    stats = inspect_cpp(original_path, scan_dir, min_coverage=1.0)
    expected = {'state':'INCOMPLETE','expected':588,'compiled':583,'missing':5,
                'vertex':132,'pixel':451,'unmatched':0,'duplicate':0}
    if any(stats.get(key)!=value for key,value in expected.items()):
        raise ReconcileBlocked('Historical cache is not valid 583/588 SMOL-V for current source inputs')

def reconcile(cache: Path, report_path: Path, scan: Path, bank_files: list[Path], archive: Path,
              *, verify_original=check_original_cache) -> dict:
    if not cache.is_file() or cache.is_symlink() or not report_path.is_file() or report_path.is_symlink():
        raise ReconcileBlocked('Expected generated shader cache/report missing or symlinked')
    current = cache.read_bytes()
    record = json.loads(report_path.read_text(encoding='utf-8'))
    if record.get('cache_sha256') != sha(current):
        raise ReconcileBlocked('Generated shader report cache SHA256 mismatch')
    scan_names = verified_inputs(scan, bank_files, record)
    current_map = entries(current)
    state = {'stage':73,'generated_entry_count':len(current_map),
             'historical_entry_count':583,'expected_total_inputs':588,
             'status':'BLOCKED_UNRECONCILED','safe_fallback_permitted':False,
             'shader_binary_equivalence_proven':False,
             'memexport_commit_permitted':False,'production_binary_approved':False}
    if set(current_map.values()) != scan_names:
        # Partial output should not be reported as all 588 inputs.
        if len(current_map) == 588:
            raise ReconcileBlocked('Generated 588-entry cache does not match SBK scan inputs')
    if len(current_map) == 583:
        state['status'] = 'KEEP_GENERATED_583_VALIDATE_WITH_PROBE56'
        return state
    if len(current_map) not in (572, 588):
        return state
    original, _ = historical(archive)
    old_map = entries(original)
    old_ids = set(old_map)
    new_ids = set(current_map)
    if len(old_ids) != 583 or len(set(old_map.values())) != 583:
        raise ReconcileBlocked('Historical diagnostic does not contain 583 distinct shader inputs')
    if len(current_map) == 572:
        # This is an actual observed regression, not a generic pass for arbitrary
        # incomplete shader sets. An unrecognized input or changed shader must
        # BLOCK the fallback; only the exact original 583 may be recovered.
        extra = new_ids - old_ids
        state['generated_entries_not_in_historical_583'] = len(extra)
        state['historical_entries_missing_from_generated'] = len(old_ids - new_ids)
        if (extra or len(old_ids - new_ids) != 11 or
            not set(old_map.values()).issubset(scan_names) or
            not set(current_map.values()).issubset(scan_names) or
            any(key[0] in MISSING for key in old_ids)):
            raise ReconcileBlocked('572-entry cache is not an exact subset of the historical 583 shader inputs')
        fallback_status = 'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_572_SUBSET_MATCH'
        fallback_record = 'REUSED_HISTORICAL_583_AFTER_STRICT_572_SUBSET_MATCH'
    else:
        extra = new_ids - old_ids
        if (not old_ids.issubset(new_ids) or len(extra) != 5 or
            {key[0] for key in extra} != MISSING or
            any(key[1] != 'VS' for key in extra) or
            set(current_map.values()) != scan_names):
            raise ReconcileBlocked('588-entry cache is not historical 583 plus exactly the known five MemExport VS')
        fallback_status = 'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_588_COMPARISON'
        fallback_record = 'REUSED_HISTORICAL_583_AFTER_STRICT_588_INPUT_MATCH'
    # Verify the actual zstd/SMOL-V layout against the NEW SBK scan before reusing it.
    # Create an isolated temporary file, never touch original game data.
    with tempfile.NamedTemporaryFile(prefix='memgate73-historical-',suffix='.cpp',dir=cache.parent,delete=False) as tmp:
        tmp.write(original)
        temp = Path(tmp.name)
    try:
        verify_original(temp, scan)
    finally:
        temp.unlink(missing_ok=True)
    generated_back = cache.with_name('shader_cache-generated73.cpp')
    if generated_back.exists():
        raise ReconcileBlocked('Refusing to overwrite preexisting compiler shader output')
    # Fail closed: any error leaves a diagnostic build incomplete, never production.
    generated_back.write_bytes(current)
    cache.write_bytes(original)
    record['cache_sha256'] = sha(original)
    record['memgate73_cache_fallback'] = {
        'status': fallback_record,
        'untrusted_generated_cache_sha256': sha(current),
        'five_new_MemExport_shaders_ignored': len(current_map) == 588,
        'historical_extra_shaders_recovered': 11 if len(current_map) == 572 else 0,
        'generated_entry_count': len(current_map),
        'production_approved': False,
    }
    report_path.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    state['status'] = fallback_status
    state['safe_fallback_permitted'] = True
    return state

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',required=True,type=Path)
    p.add_argument('--shader-report',required=True,type=Path)
    p.add_argument('--scan-dir',required=True,type=Path)
    p.add_argument('--shader-bank',required=True,type=Path,action='append')
    p.add_argument('--diagnostic',required=True,type=Path)
    p.add_argument('--report',required=True,type=Path)
    args=p.parse_args()
    result={'stage':73,'status':'BLOCKED_UNRECONCILED','memexport_commit_permitted':False,
            'production_binary_approved':False}
    try:
        result = reconcile(args.cache,args.shader_report,args.scan_dir,args.shader_bank,args.diagnostic)
    except (ReconcileBlocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result['blocked_reason'] = str(exc)[:240]
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Memgate73 shader cache: '+result.get('status','BLOCKED'))
    if 'generated_entry_count' in result:
        print(f"Generated entries: {result['generated_entry_count']} (historical expected: 583; SBK inputs: 588)")
    if result.get('status') not in ('KEEP_GENERATED_583_VALIDATE_WITH_PROBE56',
                                     'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_588_COMPARISON',
                                     'REUSED_DIAGNOSTIC43_583_AFTER_STRICT_572_SUBSET_MATCH'):
        print('BLOCKED: actual cache differs; no automatic substitution or 5-shader authorization',file=sys.stderr)
        return 2
    print('Diagnostic only: five MemExport commits remain prohibited')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
