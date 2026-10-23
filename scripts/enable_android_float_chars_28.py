#!/usr/bin/env python3
"""Insert the SDK compatibility step in the public GitHub Actions workflow."""
from pathlib import Path

path = Path('.github/workflows/build-fable2-arm64-26.yml')
s = path.read_text()
needle = '      - name: Compilar biblioteca ARM64 real\n'
addition = '''      - name: Corrigir float from_chars do ReXGlue para Android NDK
        shell: bash
        run: |
          set -euo pipefail
          python3 scripts/fix_rexglue_android_float_chars.py \\
            --sdk build/deps/rexglue-xerenge
'''
if addition in s:
    print('Workflow 28 already patched')
elif s.count(needle) == 1:
    path.write_text(s.replace(needle, addition + needle))
    print('Workflow 28 patched')
else:
    raise SystemExit('BLOCKED: unexpected workflow; no changes made')
