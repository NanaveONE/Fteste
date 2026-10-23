#!/usr/bin/env python3
"""Patch public Fable II shader workflow to publish failed-shader diagnostics PRIVATE.

The workflow still fails when 588/588 is not achieved. It does not make any
shader compile or bypass memory-export requirements.
"""
from __future__ import annotations
from pathlib import Path
import argparse

MARK = 'FABLE2_MEMEXPORT_DIAGNOSTIC_43'
PATH = '.github/workflows/build-fable2-shaders-40.yml'

OLD = '''          python3 scripts/generate_fable_shaders.py \\
            --shader-banks build/private-shader-input/Shaders.sbk \\
                           build/private-shader-input/ShadersRelease.sbk \\
            --output build/fable2-shaders \\
            --translator "$GITHUB_WORKSPACE/build/xenos-host/XenosRecomp" \\
            --header "$GITHUB_WORKSPACE/build/xenos-host/shader_common_fable_1d.h"
'''
NEW = OLD.rstrip('\n').replace('"$GITHUB_WORKSPACE/build/xenos-host/shader_common_fable_1d.h"', '"$GITHUB_WORKSPACE/build/xenos-host/shader_common_fable_1d.h" \\\n            2>&1 | tee build/shader-translation-43.log') + '\n'

VALIDATION_START = '''      - name: Verificar cobertura completa do cache Vulkan
'''
DIAG = '''      # FABLE2_MEMEXPORT_DIAGNOSTIC_43: allow shader-coverage failures to
      # expose the five privately generated HLSL sources for GPU development.
      # This is NOT a fix for memory exports, never a public Actions artifact.
      - name: Guardar diagnostico incompleto SOMENTE na release privada
        if: failure()
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.FABLE2_PRIVATE_TOKEN }}
          PRIVATE_REPO: NanaveONE/Fable2-Arquivos-Privados
          RELEASE_TAG: ${{ inputs.release_tag }}
        run: |
          set -euo pipefail
          # A failure before translation has no shader data to diagnose.
          if [[ ! -s build/shader-translation-43.log ||
                ! -s build/fable2-shaders/shader_cache.cpp ]]; then
            echo 'Sem cache parcial para diagnosticar.'
            exit 0
          fi
          test -n "$GH_TOKEN" || { echo 'BLOCKED: private token absent'; exit 2; }
          python3 scripts/report_fable_memexport_43.py \\
            --log build/shader-translation-43.log \\
            --cache build/fable2-shaders/shader_cache.cpp \\
            --hlsl-dir build/fable2-shaders/xenos-hlsl \\
            --output build/Fable2-MemExport-DIAGNOSTICO-43.zip
          gh release upload "$RELEASE_TAG" \\
            build/Fable2-MemExport-DIAGNOSTICO-43.zip \\
            --repo "$PRIVATE_REPO" --clobber
          echo 'Diagnostico privado enviado. Workflow continua FAILED ate a cobertura 588/588.' >> "$GITHUB_STEP_SUMMARY"

'''


def transform(text: str) -> str:
    if MARK in text:
        if 'tee build/shader-translation-43.log' not in text or 'report_fable_memexport_43.py' not in text:
            raise ValueError('Partial diagnostic 43 patch; stopping')
        return text
    if text.count(OLD) != 1 or text.count(VALIDATION_START) != 1:
        raise ValueError('Workflow anchors changed; stopping instead of patching blindly')
    text = text.replace(OLD, NEW, 1)
    text = text.replace('      - name: Compactar resultado para armazenamento privado\n',
                        DIAG + '      - name: Compactar resultado para armazenamento privado\n', 1)
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--root', default='.', type=Path)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    path = a.root / PATH
    try:
        original = path.read_text(encoding='utf-8')
        changed = transform(original)
        if a.check and changed != original:
            raise ValueError('Patch 43 not applied yet')
        if not a.check and changed != original:
            path.write_text(changed, encoding='utf-8')
        print('shader diagnostics 43:', 'verified' if changed == original else 'patched')
    except (ValueError, OSError) as err:
        p.exit(2, f'BLOCKED: {err}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
