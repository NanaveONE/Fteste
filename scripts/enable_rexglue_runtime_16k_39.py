#!/usr/bin/env python3
"""Make runtime builds reproducible and 16-KiB-page compatible.

Edits only the public Fteste build scripts/workflow, never game assets.
Run from the Fteste repository root. Idempotent and fail-closed.
"""
from pathlib import Path
import argparse

REXGLUE_REV = '3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b'
MARK = '# FTESTE_REXRUNTIME_16K_39'

WORKFLOW_OLD = '''          git clone --depth 1 --recurse-submodules \\
            https://github.com/shipa-2/rexglue-xerenge.git \\
            build/deps/rexglue-xerenge
'''
WORKFLOW_NEW = f'''          # Same ReXGlue revision as build-fable2-arm64-26.yml ({MARK})
          git clone https://github.com/shipa-2/rexglue-xerenge.git build/deps/rexglue-xerenge
          git -C build/deps/rexglue-xerenge checkout {REXGLUE_REV}
          git -C build/deps/rexglue-xerenge submodule update --init --recursive
'''

BUILD_OLD = '''  -DREXGLUE_ARM64_MARCH=armv8-a
cmake --build "$build" --target rexruntime --parallel "${BUILD_JOBS:-2}"
'''
BUILD_NEW = '''  -DREXGLUE_ARM64_MARCH=armv8-a \\
  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \\
  '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384'
cmake --build "$build" --target rexruntime --parallel "${BUILD_JOBS:-2}"
'''

# Guard the build input too, so a local SDK clone cannot diverge unnoticed.
BUILD_REPO_ANCHOR = '''sdk="$(cd "$sdk" && pwd)"
: "${REXSDK_DIR:=$sdk}"
'''
BUILD_REPO_NEW = f'''sdk="$(cd "$sdk" && pwd)"
: "${{REXSDK_DIR:=$sdk}}"
# {MARK} SDK revision must exactly match the already-built libfable2.so.
revision="$(git -C "$sdk" rev-parse HEAD)" || {{
  echo 'BLOCKED: ReXGlue SDK must be a git checkout' >&2; exit 2;
}}
if [[ "$revision" != "{REXGLUE_REV}" ]]; then
  echo "BLOCKED: wrong ReXGlue SDK revision $revision; expected {REXGLUE_REV}" >&2
  exit 2
fi
'''

BUILD_CHECK_ANCHOR = '''[[ -s "$artifact/librexruntime.so" && -s "$artifact/runtime-build-report.json" ]] || {
  echo 'BLOCKED: verified ARM64 runtime was not staged into build/artifacts' >&2
  exit 2
}
'''
BUILD_CHECK_NEW = BUILD_CHECK_ANCHOR + f'''# {MARK}: reject 4-KiB ELF PT_LOAD segments before uploading the artifact.
python3 "$root/scripts/check_android_16k_alignment.py" \\
  --directory "$artifact" \\
  --report "$root/build/rexruntime-arm64-alignment.json"
'''


def once(src: str, before: str, after: str, label: str) -> str:
    count = src.count(before)
    if count != 1:
        raise ValueError(f'{label}: expected exactly one original anchor, found {count}')
    return src.replace(before, after, 1)


def transformed(workflow: str, build: str) -> tuple[str, str]:
    workflow_done = WORKFLOW_NEW in workflow
    build_done = MARK in build
    if workflow_done and build_done:
        if (BUILD_NEW not in build or BUILD_REPO_NEW not in build or
                BUILD_CHECK_NEW not in build or WORKFLOW_OLD in workflow):
            raise ValueError('partial or inconsistent patch 39 detected')
        return workflow, build
    if workflow_done or build_done:
        raise ValueError('patch 39 applied only to some files; refusing half-updated build')
    workflow = once(workflow, WORKFLOW_OLD, WORKFLOW_NEW, 'workflow sdk clone')
    build = once(build, BUILD_REPO_ANCHOR, BUILD_REPO_NEW, 'SDK version preflight')
    build = once(build, BUILD_OLD, BUILD_NEW, 'NDK runtime cmake configuration')
    build = once(build, BUILD_CHECK_ANCHOR, BUILD_CHECK_NEW, 'runtime PT_LOAD check')
    return workflow, build


def apply(root: Path) -> str:
    workflow_path = root / '.github/workflows/build-android-runtime.yml'
    build_path = root / 'scripts/build_rexglue_android_sdk.sh'
    if not workflow_path.is_file() or not build_path.is_file():
        raise ValueError('Run from Fteste root; runtime build files missing')
    old_w = workflow_path.read_text(encoding='utf-8')
    old_b = build_path.read_text(encoding='utf-8')
    new_w, new_b = transformed(old_w, old_b)
    if (new_w, new_b) == (old_w, old_b):
        return 'already patched'
    # All anchors and consistency were verified before the first write.
    workflow_path.write_text(new_w, encoding='utf-8')
    build_path.write_text(new_b, encoding='utf-8')
    return 'patched'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path('.'))
    args = ap.parse_args()
    try:
        print('runtime 39:', apply(args.root.resolve()))
    except (OSError, ValueError) as exc:
        ap.exit(2, f'BLOCKED: {exc}\n')


if __name__ == '__main__':
    main()
