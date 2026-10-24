#!/usr/bin/env python3
"""In-memory verification of the exact downstream Plume 61/71/72 suffix.
No source rewrite. Unknown changes fail closed to preserve earlier CI.
"""

STAGE71 = '# FABLE2_PLUME_61_CERTIFIED_GATE: keep immutable 55, add opt-in bridge.\nplume_overlay="$root/build/fable2-plume-overlay-61"\npython3 "$root/scripts/apply_fable_plume61.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume55_overlay" --overlay "$plume_overlay"\nif [[ "${FABLE2_MEMGATE71_DIAGNOSTIC:-0}" == "1" ]]; then\n  # The SDK must enroll real guest/runtime writer scopes as well as Plume ABI.\n  if ! python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR" --check >/dev/null 2>&1; then\n    python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR"\n  fi\n  python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR" --check\nfi\nbuild="$root/build/fable2-gpu-android-arm64"\n'
STAGE72 = '# FABLE2_PLUME_61_CERTIFIED_GATE: keep immutable 55, add opt-in bridge.\nplume_overlay="$root/build/fable2-plume-overlay-61"\npython3 "$root/scripts/apply_fable_plume61.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume55_overlay" --overlay "$plume_overlay"\nif [[ "${FABLE2_MEMGATE71_DIAGNOSTIC:-0}" == "1" ]]; then\n  # Memgate72: new isolated Plume overlay; stage61 remains hash-verified.\n  plume72_overlay="$root/build/fable2-plume-overlay-72"\n  python3 "$root/scripts/apply_fable_plume72.py" \\\n    --base-overlay "$plume_overlay" --overlay "$plume72_overlay"\n  python3 "$root/scripts/apply_fable_plume72.py" \\\n    --base-overlay "$plume_overlay" --overlay "$plume72_overlay" --check \\\n    --report "$root/build/memgate72-plume-hooks.json"\n  plume_overlay="$plume72_overlay"\n  # The SDK must enroll real guest/runtime writer scopes as well as Plume ABI.\n  if ! python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR" --check >/dev/null 2>&1; then\n    python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR"\n  fi\n  python3 "$root/scripts/patch_rex_memgate71_sdk.py" --sdk "$REXSDK_DIR" --check\n  if ! python3 "$root/scripts/patch_rex_memgate72_sdk.py" --sdk "$REXSDK_DIR" --check >/dev/null 2>&1; then\n    python3 "$root/scripts/patch_rex_memgate72_sdk.py" --sdk "$REXSDK_DIR"\n  fi\n  python3 "$root/scripts/patch_rex_memgate72_sdk.py" --sdk "$REXSDK_DIR" --check\nfi\nbuild="$root/build/fable2-gpu-android-arm64"\n'
RESTORED = 'build="$root/build/fable2-gpu-android-arm64"\n'


# Exact inverse for the variable rename introduced by overlay61, verified
# alongside its complete 71/72 suffix. The source file is NEVER rewritten.
STAGE55_COMPOSED = '# FABLE2_PLUME_55_BUILDSCRIPT: keep immutable overlay53 for verified input.\nplume53_overlay="$root/build/fable2-plume-overlay-53"\npython3 "$root/scripts/apply_fable_plume53.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume52_overlay" --overlay "$plume53_overlay"\nplume55_overlay="$root/build/fable2-plume-overlay-55"\npython3 "$root/scripts/apply_fable_plume55.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume53_overlay" --overlay "$plume55_overlay"\n'
STAGE55_LEGACY = '# FABLE2_PLUME_55_BUILDSCRIPT: keep immutable overlay53 for verified input.\nplume53_overlay="$root/build/fable2-plume-overlay-53"\npython3 "$root/scripts/apply_fable_plume53.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume52_overlay" --overlay "$plume53_overlay"\nplume_overlay="$root/build/fable2-plume-overlay-55"\npython3 "$root/scripts/apply_fable_plume55.py" \\\n  --xerenge-root "$root/external/Xerenge" \\\n  --base-overlay "$plume53_overlay" --overlay "$plume_overlay"\n'

def canonical_stage55(source: str) -> str:
    marker = '# FABLE2_PLUME_61_CERTIFIED_GATE'
    if marker not in source:
        # A fragment of the later layer must never be mistaken for a valid 55.
        if ('patch_rex_memgate71_sdk.py' in source or
                'plume55_overlay=' in source or 'apply_fable_plume72.py' in source):
            raise ValueError('Unknown partial Plume downstream integration')
        return source
    if source.count(marker) != 1:
        raise ValueError('Duplicate downstream Plume61 marker')
    for known in (STAGE72, STAGE71):
        if source.count(known) != 1:
            continue
        # Require the renamed exact Plume55 definition immediately before the
        # known suffix. Earlier CI then verifies exact 55/53/52 layers itself.
        if source.count(STAGE55_COMPOSED + known) != 1 or STAGE55_LEGACY in source:
            raise ValueError('Modified downstream Plume55 base or integration')
        old = source.replace(STAGE55_COMPOSED + known,
                             STAGE55_LEGACY + RESTORED, 1)
        if '# FABLE2_PLUME_61_CERTIFIED_GATE' in old or 'plume55_overlay=' in old:
            raise ValueError('Incomplete downstream Plume normalization')
        return old
    raise ValueError('Modified downstream Plume61/71/72 chain')
