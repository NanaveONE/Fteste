#!/usr/bin/env python3
"""Wire the checked-out ReXGlue Dear ImGui headers into the Fable Android target."""
from pathlib import Path
import argparse

ANCHOR = 'build="$root/build/fable2-android-arm64"'
INSERT = '''# ImGui is a private SDK transitive header included by rex/rex_app.h.
# The game target does not inherit its include directory automatically.
imgui_header="$(find "$REXSDK_DIR/thirdparty" -type f -name imgui.h -print -quit)"
if [[ -z "$imgui_header" ]]; then
    echo 'BLOCKED: SDK thirdparty/imgui.h missing; check recursive submodules' >&2
    exit 2
fi
imgui_dir="$(dirname "$imgui_header")"
[[ -s "$imgui_dir/imgui.h" ]] || { echo 'BLOCKED: imgui.h empty' >&2; exit 2; }
echo "[android] Dear ImGui include directory: $imgui_dir"
'''

def patch(text):
    if 'imgui_header="$(find "$REXSDK_DIR/thirdparty"' in text:
        return text
    if text.count(ANCHOR) != 1:
        raise ValueError('Expected exactly one build directory anchor')
    if text.count("'-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics'") != 1:
        raise ValueError('Expected CMAKE_CXX_FLAGS anchor missing')
    text = text.replace(ANCHOR, INSERT + '\n' + ANCHOR, 1)
    text = text.replace("'-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics'", '"-DCMAKE_CXX_FLAGS=-march=armv8-a -moutline-atomics -I${imgui_dir}"', 1)
    return text

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--build-script',type=Path,default=Path('scripts/build_android_native.sh'))
    args=ap.parse_args()
    old=args.build_script.read_text()
    new=patch(old)
    if new != old:
        args.build_script.write_text(new)
        print('OK: Dear ImGui include path enabled for Android CMake')
    else:
        print('OK: already enabled')

if __name__=='__main__':main()
