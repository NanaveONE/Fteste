#!/usr/bin/env python3
"""Opt-in PRIVATE GPU compiler diagnostic: accept only the known Fable II 583/588 cache.

Never authorizes a production APK. The generated cache hash is bound to the
SBK input report, and all 583 compiled shader input identities are matched to
the private MemExport43 cache even if generated shader bytes change.
All actual raw shader bytes stay in ignored local build/ and private releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile

def inspect_cpp(*args, **kwargs):
    # Import at call time so pure evidence tests require no actual shader data.
    try:
        from scripts.validate_xenosrecomp_cache import inspect_cpp as verify
    except ModuleNotFoundError:
        from validate_xenosrecomp_cache import inspect_cpp as verify
    return verify(*args, **kwargs)

KNOWN_MISSING = frozenset({
    '17A0FEDEF93DAE25', '1CEC1A730807EC21', '5243696187782727',
    'AC0C424248A6B1AD', 'DB2ACD9856EB8E28',
})
EXPECTED = 588
COMPILED = 583


class ProbeError(ValueError):
    pass


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def compiled_shader_identities(cache_bytes: bytes) -> tuple[tuple[int, str, str], ...]:
    """Identify guest inputs, not compiler output (which can change between builds).

    Each entry is keyed by XenosRecomp's shader hash, stage, and SHA-256 of
    the original SBK container in the input filename. A changed shader set
    is never accepted just because the number of entries is still 583.
    """
    try:
        source = cache_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ProbeError('Invalid shader cache text') from exc
    table = re.search(r'ShaderCacheEntry\s+g_shaderCacheEntries\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;',
                      source, re.S)
    require(table is not None, 'Shader cache identity table missing')
    row = re.compile(
        r'\s*\{\s*(0[xX][\da-fA-F]+)\s*,\s*\d+\s*,\s*\d+\s*,\s*'
        r'\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*"([^"\n]+)"\s*\},?\s*')
    identities = []
    for line in table.group(1).splitlines():
        if not line.strip():
            continue
        entry = row.fullmatch(line)
        require(entry is not None, 'Unrecognized shader cache identity entry')
        name = Path(entry.group(2).replace('\\', '/')).name
        match = re.fullmatch(r'(VS|PS)_([\da-fA-F]{64})\.bin', name, re.I)
        require(match is not None, 'Shader cache entry lacks original SBK container SHA-256')
        identities.append((int(entry.group(1), 16), match.group(1).upper(),
                           match.group(2).lower()))
    require(len(identities) == COMPILED, 'Private cache does not contain exactly 583 entries')
    require(len(set(identities)) == COMPILED and
            len({(stage, sha) for _, stage, sha in identities}) == COMPILED,
            'Private cache contains duplicate/conflicting shader identities')
    require(sum(stage == 'VS' for _, stage, _ in identities) == 132 and
            sum(stage == 'PS' for _, stage, _ in identities) == 451,
            'Private shader identities have incorrect stage counts')
    return tuple(sorted(identities))


def validate_evidence(cache_bytes: bytes, shader_report: dict, diagnostic: dict,
                      original_cache: bytes, stats: dict) -> dict:
    """Pure, testable gate; no games and no private shaders are bundled here."""
    actual_sha = digest(cache_bytes)
    require(shader_report.get('source_title') == 'Fable II', 'Not a Fable II cache')
    require(shader_report.get('input_kind') == 'shader_banks', 'Source is not verified SBK banks')
    require(shader_report.get('extracted_containers') == EXPECTED,
            'Not the expected 588 shader containers')
    require(shader_report.get('cache_sha256') == actual_sha,
            'Shader report hash does not match actual cache')
    banks = shader_report.get('shader_banks')
    require(isinstance(banks, list) and len(banks) == 2, 'Expected exactly two input SBK banks')
    require({str(b.get('filename', '')).casefold() for b in banks} ==
            {'shaders.sbk', 'shadersrelease.sbk'}, 'Unexpected SBK input bank names')
    require(all(re.fullmatch('[0-9a-fA-F]{64}', str(b.get('sha256', ''))) for b in banks),
            'SBK provenance sha256 missing')
    require(diagnostic.get('status') == 'INCOMPLETE_MEMEXPORT_UNIMPLEMENTED' and
            diagnostic.get('total_shaders') == EXPECTED and
            diagnostic.get('translated') == COMPILED and
            diagnostic.get('skipped') == 5, 'Unexpected private diagnostic counts')
    failed = diagnostic.get('shader_failures')
    require(isinstance(failed, list) and len(failed) == 5 and
            {str(x.get('shader_hash', '')).upper() for x in failed} == KNOWN_MISSING,
            'Missing shaders differ from five known MemExport vertex shaders')
    require(all(x.get('hlsl_found') is True for x in failed),
            'Private diagnostic has missing HLSL source')
    # Binary byte equality is too strict for a re-generated cache: DXC,
    # compression and header changes can change the output without changing
    # the 583 guest shader inputs. Only relax it for an explicit, compiler-only
    # diagnostic, and only if the full set of original shader identities agrees.
    drift = cache_bytes != original_cache
    if drift:
        require(compiled_shader_identities(cache_bytes) ==
                compiled_shader_identities(original_cache),
                'Cache differs from private 43 diagnostic: shader input identities changed')
    require(stats.get('state') == 'INCOMPLETE' and stats.get('expected') == EXPECTED and
            stats.get('compiled') == COMPILED and stats.get('missing') == 5 and
            stats.get('vertex') == 132 and stats.get('pixel') == 451 and
            stats.get('unmatched') == 0 and stats.get('duplicate') == 0,
            'Cached SPIR-V coverage is not precisely 132 VS + 451 PS')
    return {
        'status': 'PRIVATE_ARM64_GPU_PROBE56_ONLY',
        'title': 'Fable II', 'source': 'Shaders.sbk + ShadersRelease.sbk',
        'expected': EXPECTED, 'compiled': COMPILED, 'missing': 5,
        'missing_hashes': sorted(KNOWN_MISSING),
        'cache_sha256': actual_sha,
        'diagnostic43_cache_sha256': digest(original_cache),
        'toolchain_drift_detected': drift,
        'shader_binary_equivalence_proven': not drift,
        'identity_comparison': 'same 583 XenosRecomp input shader hashes, stages and SBK container SHA-256' if drift else 'byte-identical caches',
        'production_approved': False,
        'guest_memexport_execution_proven': False,
        'notes': ('Compiler probe only: newly generated binary shader modules are NOT '
                  'proven equivalent to diagnostic43 when drift is detected. '
                  'Five MemExport vertex shaders still missing; NOT a playable APK.'),
    }


def validate(cache: Path, scan_dir: Path, shader_report: Path, diagnostic_zip: Path) -> dict:
    if not all(p.is_file() for p in [cache, shader_report, diagnostic_zip]) or not scan_dir.is_dir():
        raise ProbeError('Private cache, scan directory, report or 43 diagnostic missing')
    with ZipFile(diagnostic_zip, 'r') as z:
        with z.open('diagnostic/memexport-43.json') as f:
            diagnostic = json.load(f)
        with z.open('partial-cache/shader_cache.cpp') as f:
            old_cache = f.read()
    shader_info = json.loads(shader_report.read_text(encoding='utf-8'))
    # Require 100% for the structural state classification: 583/588 must
    # remain INCOMPLETE. The opt-in evidence gate below separately
    # authorizes only the exact known 583/588 diagnostic (never APK).
    stats = inspect_cpp(cache, scan_dir, min_coverage=1.0)
    return validate_evidence(cache.read_bytes(), shader_info, diagnostic, old_cache, stats)


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--cache', type=Path, required=True)
    a.add_argument('--scan-dir', type=Path, required=True)
    a.add_argument('--shader-report', type=Path, required=True)
    a.add_argument('--diagnostic', type=Path, required=True)
    a.add_argument('--report', type=Path)
    args = a.parse_args()
    try:
        result = validate(args.cache, args.scan_dir, args.shader_report, args.diagnostic)
    except (ProbeError, KeyError, BadZipFile, OSError, ValueError) as exc:
        a.exit(2, f'BLOCKED GPU PROBE56: {exc}\n')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print('PASS: Fable II 583/588 diagnostic shader input identities verified')
    if result['toolchain_drift_detected']:
        print('WARNING: binary shader cache differs from diagnostic43; equivalence NOT proven')
    print('PROBE ONLY: five missing MemExport VS excluded; production/APK still forbidden')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
