#!/usr/bin/env python3
"""Recompile Fable II GOTY XEX to PRIVATE host-side C++ with the actual upstream manifest.

This is deliberately separate from Android/Plume/APK builds. No game bytes, generated
sources, or logs are uploaded. Requires Linux x86_64 for execution (Termux cannot
execute the uploaded x86_64 codegen natively).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib

EXPECTED_NAME = 'fable_2'
EXPECTED_XEX = 'default.xex'
EXPECTED_GENERATED = 'generated/default'
EXPECTED_MACHINE = 62  # ELF EM_X86_64


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def relative_name(value: str) -> Path:
    p = PurePosixPath(value)
    if (not value or '\\' in value or p.is_absolute()
            or any(part in ('', '.', '..') for part in p.parts)
            or p.as_posix().startswith('-')):
        raise ValueError('unsafe relative include path in upstream manifest')
    return Path(*p.parts)


def codegen_artifact(tool: Path) -> dict:
    tool = tool.resolve(strict=True)
    if tool.name != 'rexglue' or not tool.is_file() or not os.access(tool, os.X_OK):
        raise ValueError('expected executable Linux rexglue from the codegen artifact')
    with tool.open('rb') as fp:
        hdr = fp.read(20)
    if (len(hdr) < 20 or hdr[:6] != b'\x7fELF\x02\x01'
            or struct.unpack_from('<H', hdr, 18)[0] != EXPECTED_MACHINE):
        raise ValueError('rexglue must be a little-endian ELF64 x86_64 executable')
    manifest = tool.parent / 'codegen-report.json'
    if not manifest.is_file():
        raise ValueError('codegen-report.json missing; extract the COMPLETE host Codegen ZIP')
    report = json.loads(manifest.read_text(encoding='utf-8'))
    if report.get('kind') != 'linux_x86_64_rexglue_codegen' or report.get('game_files_included') is not False:
        raise ValueError('not the expected open-source Codegen Linux artifact')
    for name in ('rexglue', 'librexruntime.so'):
        data = report.get('files', {}).get(name, {})
        path = tool.parent / name
        if not path.is_file() or path.stat().st_size != data.get('bytes') or digest(path) != data.get('sha256'):
            raise ValueError('Codegen artifact file missing or checksum mismatch: ' + name)
    return report


def official_manifest(source: Path) -> tuple[list[Path], dict]:
    if not (source / 'CMakeLists.txt').is_file() or not (source / 'generated/rexglue.cmake').is_file():
        raise ValueError('the Fable-2-Recomp public SOURCE checkout is missing/incomplete')
    manifest = source / 'fable_2_manifest.toml'
    if not manifest.is_file():
        raise ValueError('upstream fable_2_manifest.toml missing')
    with manifest.open('rb') as fp:
        config = tomllib.load(fp)
    project, entry = config.get('project', {}), config.get('entrypoint', {})
    if (project.get('name') != EXPECTED_NAME or project.get('game_root') != '.'
            or entry.get('file_path') != EXPECTED_XEX
            or entry.get('out_directory_path') != EXPECTED_GENERATED):
        raise ValueError('unsupported Fable-2-Recomp manifest layout; review upstream')
    includes = entry.get('includes', [])
    if not isinstance(includes, list) or 'fable2_switch_tables.toml' not in includes:
        raise ValueError('Fable II switch tables must be included from official manifest')
    names = [Path('fable_2_manifest.toml')]
    for include in includes:
        if not isinstance(include, str):
            raise ValueError('unsupported include in manifest')
        rel = relative_name(include)
        if not (source / rel).is_file():
            raise ValueError(f'upstream include missing: {rel}')
        names.append(rel)
    return names, config


def compatible_xex(xex: Path, source: Path) -> tuple[str, str]:
    if not xex.is_file():
        raise ValueError('input default.xex missing')
    with xex.open('rb') as source_file:
        if source_file.read(4) != b'XEX2':
            raise ValueError('input is not a genuine Xbox 360 XEX2 file')
    sha = digest(xex)
    catalog = source / 'constants/game_versions.json'
    if not catalog.is_file():
        raise ValueError('missing official Fable-2-Recomp version catalog')
    versions = json.loads(catalog.read_text(encoding='utf-8'))['versions']
    candidates = [p for p in versions if p.get('hash', '').lower() == sha
                  and p.get('xexSize') == xex.stat().st_size]
    if len(candidates) != 1 or candidates[0].get('compatible') is not True:
        raise ValueError('XEX not a supported original Fable II GOTY edition')
    return str(candidates[0]['id']), sha


def preflight(repo: Path, source: Path, xex: Path, tool: Path, output: Path) -> dict:
    repo, source, xex, tool, output = [p.expanduser().resolve() for p in (repo, source, xex, tool, output)]
    allowed = (repo / 'build').resolve()
    if output != allowed and allowed not in output.parents:
        raise ValueError('private work/output MUST stay under Fteste/build/ (git-ignored)')
    if output.exists():
        raise ValueError('output already exists; do not mix partial or different game outputs')
    if output in source.parents or output == source:
        raise ValueError('output cannot overwrite original Fable-2-Recomp sources')
    artifact = codegen_artifact(tool)
    public_files, config = official_manifest(source)
    profile, sha = compatible_xex(xex, source)
    return {'repo': repo, 'source': source, 'xex': xex, 'tool': tool, 'output': output,
            'public_files': public_files, 'config': config,
            'profile': profile, 'xex_sha256': sha,
            'sdk_git_commit': artifact['sdk_git_commit']}


def generate(plan: dict, *, runner=subprocess.run) -> dict:
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise ValueError('the host Codegen runs only on Linux x86_64; NOT on Android/Termux')
    output: Path = plan['output']
    output.mkdir(parents=True, exist_ok=False)
    # Only private files under build/. Never touch src/, the Git submodule or the original dump.
    for relative in plan['public_files']:
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plan['source'] / relative, dest)
    shutil.copy2(plan['xex'], output / 'default.xex')
    log = output / 'codegen.log'
    with log.open('w', encoding='utf-8') as fd:
        fd.write('Fable II host codegen: private local run; never upload this directory.\n')
        fd.flush()
        # Check that executable and the shared runtime really load on the current Linux host.
        runner([str(plan['tool']), '--version'], cwd=output, stdout=fd,
               stderr=subprocess.STDOUT, check=True)
        runner([str(plan['tool']), 'codegen', 'fable_2_manifest.toml'], cwd=output,
               stdout=fd, stderr=subprocess.STDOUT, check=True)
    index = output / 'generated/default/sources.cmake'
    if not index.is_file():
        raise ValueError('ReXGlue did not write generated/default/sources.cmake')
    contents = index.read_text(encoding='utf-8')
    if not re.search(r'\bGENERATED_SOURCES\b', contents) or '.cpp' not in contents:
        raise ValueError('sources.cmake has no C++ guest sources')
    cpp = list((output / 'generated/default').rglob('*.cpp'))
    if not cpp:
        raise ValueError('ReXGlue generated zero real guest .cpp files')
    report = {'state': 'GUEST_CPP_GENERATED', 'game': 'Fable II',
              'profile': plan['profile'], 'xex_sha256': plan['xex_sha256'],
              'sdk_git_commit': plan['sdk_git_commit'],
              'translation_units': len(cpp),
              'guest_cpp_bytes': sum(p.stat().st_size for p in cpp),
              'manifest_sha256': digest(output / 'fable_2_manifest.toml'),
              'privacy': 'Never commit or upload this folder. No source bytes in report.',
              'next': 'Validate generated code and compile ARM64 libfable2.so against same Android SDK source.'}
    (output / 'codegen-summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--repo-root', type=Path, default=root)
    parser.add_argument('--source', type=Path, default=root / 'external/Fable-2-Recomp')
    parser.add_argument('--xex', type=Path, required=True)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=root / 'build/fable2-guest-codegen-private')
    parser.add_argument('--check', action='store_true', help='Validate all inputs without copying/generating files')
    args = parser.parse_args()
    try:
        p = preflight(args.repo_root, args.source, args.xex, args.tool, args.output)
        print(f'OK: supported Fable II {p["profile"]}; host tool and official manifest verified')
        print('OK: no data/ folder or Android NDK required for this guest C++ generation step')
        if args.check:
            return 0
        result = generate(p)
        print(f'OK: {result["translation_units"]} real guest .cpp files produced privately in build/')
        return 0
    except (ValueError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        print('Keep private build/ logs locally; never upload game code or default.xex to GitHub.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
