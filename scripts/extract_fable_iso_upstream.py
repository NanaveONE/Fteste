#!/usr/bin/env python3
"""Install a private Fable II ISO dump using upstream himdo/Fable-2-Recomp x360extract.

Unlike the Android GDFX/SAF reader, this route executes the upstream .NET 8
command-line tool unchanged. Nothing proprietary enters the git repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def validate_xex(xex: Path, catalog_path: Path) -> dict:
    versions = json.loads(catalog_path.read_text(encoding='utf-8'))['versions']
    digest = hashlib.sha256()
    with xex.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    sha = digest.hexdigest().lower()
    profile = next((v for v in versions if v.get('hash', '').lower() == sha
                    and v.get('xexSize') == xex.stat().st_size), None)
    if profile is None or not profile.get('compatible', False):
        raise ValueError('ISO não contém uma versão GOTY suportada pelo Fable-2-Recomp')
    return profile


def validate_data(root: Path, profile: dict) -> None:
    if not (root / 'data').is_dir():
        raise ValueError('O extrator não produziu data/')
    for item in profile.get('requiredFiles', []):
        if not (root / item).is_file():
            raise ValueError('Arquivo obrigatório ausente após extração: ' + item)
    for item in profile.get('rejectFiles', []):
        if (root / item).exists():
            raise ValueError('Conteúdo incompatível misturado com GOTY: ' + item)


def install_iso(iso: Path, output: Path, upstream: Path) -> str:
    iso = iso.expanduser().resolve(strict=True)
    output = output.expanduser().resolve()
    upstream = upstream.expanduser().resolve()
    project = upstream / 'tools/x360extract/X360Extract.csproj'
    catalog = upstream / 'constants/game_versions.json'
    if not project.is_file() or not catalog.is_file():
        raise ValueError('Submódulo himdo/Fable-2-Recomp incompleto')
    if iso.suffix.lower() not in ('.iso', '.rumb') or not iso.is_file():
        raise ValueError('Forneça uma ISO/RUMB local original do Xbox 360')
    if output.exists():
        raise ValueError('Destino já existe; não substituir arquivos comerciais existentes')
    if shutil.which('dotnet') is None:
        raise ValueError('Instale o .NET 8 SDK no computador Linux/Windows')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.fable2-iso-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'game'
        staging.mkdir()
        command = ['dotnet', 'run', '--project', str(project), '--configuration', 'Release',
                   '--', str(iso), '--out', str(staging), '--quiet']
        # Two-phase extraction from the SAME official game's repo: reject a
        # wrong XEX before spending disk space on gigabytes of game content.
        subprocess.run([*command, '--files', 'default.xex'], check=True)
        profile = validate_xex(staging / 'default.xex', catalog)
        subprocess.run([*command, '--files', 'data'], check=True)
        validate_data(staging, profile)
        with (staging / '.import-complete').open('w', encoding='utf-8') as marker:
            marker.write('Fable II ' + profile['id'] + ' upstream x360extract\n')
            marker.flush()
            os.fsync(marker.fileno())
        # Atomic publish in the same filesystem; existing data is never overwritten.
        staging.rename(output)
        return str(profile['id'])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--upstream', type=Path, default=Path(__file__).resolve().parents[1] / 'external/Fable-2-Recomp')
    args = p.parse_args()
    try:
        profile = install_iso(args.iso, args.output, args.upstream)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as e:
        p.exit(2, 'BLOCKED: ' + str(e) + '\n')
    print('OK: Fable II original', profile, 'extraído em', args.output)
    print('Os dados são privados. Não envie ISO, XEX ou data/ ao GitHub.')


if __name__ == '__main__':
    main()
