# Fable II Android: native entrypoint and overlay (in progress)

These are concrete integration sources for the intended Fable II Android port,
not a working APK or a replacement for the recompiled game.

## Adapted pieces

- `android/AndroidManifest.xml`: separate Fable II application, landscape SDL Activity.
- `android/java/com/nanaveone/fable2/Fable2Activity.java`: loads
  `libc++_shared.so`, `librexruntime.so`, then `libfable2.so`; passes
  `--game_data_root=<app external files>/game` to the native entrypoint.
- `scripts/prepare_android_target.py`: creates a **local copy** of the
  Fable-2-Recomp sources with Android CMake using `add_library(fable_2 SHARED ...)`
  and `OUTPUT_NAME fable2`. Nothing changes inside tracked submodules.
- `scripts/verify_port_layout.py`: checks integration points against the
  checked-out Fable II and Xerenge revisions.

## How to check the integration on Termux

```sh
cd ~/Fteste
git pull
git submodule update --init --recursive
pkg install python -y
python scripts/verify_port_layout.py
python -m unittest discover -s tests -v
python scripts/prepare_android_target.py
```

The local overlay is written to `build/fable2-android-worktree` (gitignored).
It removes `data/`, `.xex`, `.iso` and other local game files from the copy.
Do not upload personal game dumps, generated code, or build output.

## Still required for a *playable* game

1. Build/reconcile Android ReXGlue runtime and guest-codegen tool for the
   specific Fable II version. `generated/rexglue.cmake` and recompiled guest
   translation units may need to be generated locally from your legitimate game.
2. Make the Fable `REX_DEFINE_APP` entry produce an SDL compatible `SDL_main`.
   The Java file expects `libfable2.so` and cannot supply it by itself.
3. Port Fable II GPU draw calls/shaders to Vulkan. The Xerenge Plume renderer
   includes Burnout-specific handling; it cannot be relabeled as Fable's GPU.
   The original Fable CMake still selects the `xenos` plugin (not an Android
   Vulkan backend). This is the **main blocker**.
4. Adapt game-specific Win32 APIs, image loading, save paths, audio and input.
5. Compile, package an APK with SDL3's Java classes and NDK libraries, then
   test launching, rendering and gameplay on target hardware.

A passing CI check here confirms only the source layout and overlay generator;
it must not be presented as a successful Android port.

## Upstreams and licenses

- https://github.com/himdo/Fable-2-Recomp — MIT license (check actual files).
- https://github.com/shipa-2/Xerenge — GPL-3.0-or-later (verify third-party licenses).

Reusing derived Xerenge code in a distributed app requires complying with its
copyleft license and applicable third-party notices. No copyrighted game files
are included in this repository.

## Integração 02: pasta do jogo e empacotamento nativo

- `Fable2LauncherActivity.java`: seletor de pasta do Android 12 via Storage
  Access Framework, com cópia em segundo plano de `default.xex` e `data/`
  para a pasta privada do app. **Não extrai ISOs** e não traz dados comerciais.
- `Fable2Activity.java`: Activity SDL3 já preparada para carregar bibliotecas
  Fable II, sem Burnout.
- `scripts/prepare_android_target.py`: agora seleciona `GPU_PLUGINS plume`
  no Android e `xenos` no desktop. Isso só configura a intenção do backend;
  **o Plume de Xerenge ainda NÃO renderiza Fable II**.
- `scripts/package_android_apk.sh`: empacota e assina um APK SOMENTE quando
  o código nativo ARM64, runtime e plugin Vulkan necessários já existirem.
  Ausência de qualquer `.so` impede gerar um APK fictício.
- `docs/GPU-PORT-ROADMAP.md`: delimita o trabalho gráfico restante.

### Pré-requisitos para empacotamento (ainda faltam as bibliotecas reais)

`ANDROID_HOME`, `ANDROID_NDK_HOME`, `SDL_JAVA_DIR` (fontes Java SDL3) e
`NATIVE_LIB_DIR` (bibliotecas ARM64 reais) devem apontar para pastas locais.
O APK assinado não comprova que o jogo funciona, e o empacotador não constrói
as bibliotecas nativas por conta própria.
