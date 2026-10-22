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

## Integração 03: runtime, entrada e controles

- O overlay CMake compila `fable_2` como `libfable2.so` para Android e inclui
  `port/android/native/fable2_touch.cpp` como fonte do jogo.
- `src/main.cpp` (na cópia local) desativa dois probes de exceção/threads que
  chamam diretamente a API Win32. Isso **não** prova que os demais arquivos
  Fable II sejam compatíveis com Android.
- `src/core/fable_2_app.h` (na cópia local) escolhe `plume` como nome padrão
  de plugin de GPU no Android, mantém `xenos` no desktop e move saves/cache
  para a pasta do aplicativo (`FABLE2_USER_ROOT`).
- `Fable2TouchControls.java` + JNI/SDL3 implementam sticks esquerdo/direito,
  A/B/X/Y, direcional, gatilhos, botões de ombro, Menu e View com multitouch.
- `scripts/check_native_libs.py` verifica arquitetura ELF, símbolos públicos
  `rex_gpu_create` / `rex_gpu_abi_version` e dependências indevidas do Burnout.
- `scripts/compare_sdk_abi.py` compara ABI público e headers dos SDKs; APIs
  iguais não garantem que bibliotecas sejam compatíveis em tempo de execução.
- `scripts/build_android_native.sh` contém a invocação concreta do NDK, mas
  exige código do jogo local, SDK Android recompilável e codegen **do host**.

### Comandos de preparação

```bash
cd ~/Fteste
git submodule update --init --recursive
python3 -m unittest discover -s tests -v
python3 scripts/prepare_android_target.py
```

Para uma tentativa de compilação nativa em máquina Linux com NDK instalado:

```bash
export ANDROID_NDK_HOME=/caminho/do/ndk
export FABLE2_GAME_ROOT=/caminho/para/arquivos-extraidos-proprios
export REXSDK_DIR=/caminho/para/rexglue-sdk-android-compativel
export FABLE2_CODEGEN_TOOL=/caminho/para/rexglue-host-x86_64
bash scripts/build_android_native.sh
```

O build nativo ainda pode falhar porque o SDK usado pelo Fable II requer
portabilidade para Android e o Plume do Xerenge não suporta automaticamente
os comandos/shaders de Fable II. **Sem um plugin GPU adaptado e bibliotecas
compiladas, não existe APK jogável.**

### Licenças

O código de joystick virtual deriva da implementação de referência SDL3
do Xerenge e está identificado como GPL-3.0-or-later; ao redistribuí-lo,
cumpra a GPL e preserve as licenças dos demais componentes.

## Integração 04: construir Plume com shaders do Fable II

O overlay Android não pede mais `GPU_PLUGINS plume` ao SDK como se o SDK já distribuísse esse plugin. O alvo `librexgpu-plume.so` é construído à parte a partir dos **arquivos-fonte do Xerenge**, usando **shaders específicos da sua cópia de Fable II**.

1. Instale ferramentas host de Xerenge/XenosRecomp (ver `CHANGELOG-04.md`).
2. Execute `scripts/generate_fable_shaders.py` com `default.xex` legítimo ou imagem já decodificada. Os resultados ficam no diretório ignorado `build/fable2-shaders/`.
3. Compile o backend Vulkan com `scripts/build_fable_gpu.sh` e um SDK ReXGlue com Android compatível.
4. Estude os relatórios de `scripts/gpu_log_report.py` e corrija os comandos GPU que ainda falharem.

**Atenção:** shader scan é somente uma etapa; não supre shaders montados em tempo de execução, recursos de GPU específicos do Fable II ou testes de gameplay. Não existe APK jogável validado nesta etapa.

## Integração 05: impedir bibliotecas sem jogo e fechar dependências

- O gerador host ReXGlue agora roda **antes** da configuração CMake Android.
  Se não existir `generated/default/sources.cmake` com fontes guest `.cpp`, a
  compilação para: não entrega uma biblioteca que contenha só o launcher.
- O SDK selecionado precisa fornecer `SDL_main` e arquivos nativos Android;
  `python3 scripts/audit_android_sdk.py --sdk /SDK-ANDROID` registra o relatório.
- `python3 scripts/stage_android_libs.py --help` mostra como reunir as bibliotecas
  ARM64 realmente compiladas e fechar `DT_NEEDED`. Dependências apenas via
  `dlopen` precisam ser incluídas explicitamente com `--extra-lib`.
- O APK só deve ser empacotado após validar `build/android-native-stage/`.

Consulte `CHANGELOG-05.md` para o fluxo completo. Nenhuma destas verificações
substitui compilar e executar o jogo no celular.

## Integração 06: tentativa de compilação completa e diagnósticos no Android

Agora há um fluxo único (sem gerar APK de mentira) para tentar as etapas em
sequência: código do jogo -> shaders Fable -> ARM64 ReXGlue -> GPU Vulkan ->
ELF -> APK assinado. **Ele falhará sem um `default.xex` real compatível e
sem NDK/SDK instalados**, conforme esperado. Executar testes de Python não
compila Fable II.

```bash
# Em um computador Linux x86_64 com Android SDK/NDK instalados:
git submodule update --init --recursive
bash scripts/setup_gpu_dependencies.sh
bash scripts/build_host_tools.sh
# Execute os export FABLE2_* impressos na tela pelo script acima.
# Configure os caminhos privados impressos pelo build_host_tools.sh e demais envs.
export FABLE2_GAME_ROOT=/pasta/privada/Fable2-extraido
export ANDROID_NDK_HOME=/seu/ndk
export ANDROID_HOME=/seu/android-sdk
export REXSDK_DIR="$PWD/build/deps/rexglue-xerenge"
export PLUME_ROOT="$PWD/build/deps/plume-xerenge"
export XENOS_RECOMP_ROOT="$PWD/build/deps/XenosRecomp-xerenge"
bash scripts/attempt_playable_build.sh --check
bash scripts/attempt_playable_build.sh --build
```

Após gerar um APK **real** e importar os dados no telefone, usar
`bash scripts/device_smoke_test.sh` via ADB. A coleta verifica sinais de
falha, **não comprova gameplay, FPS, áudio ou salvamento**.

Não comite arquivos comerciais nem envie o jogo para GitHub Actions. Os scripts
que executam `cmake` e XenosRecomp dependem de um host Linux x86_64; Termux
sozinho não é um substituto direto do toolchain Linux/Android NDK.
