# Próxima fase: compilar `libfable2.so` real no Linux x86-64

**Jogo:** Fable II GOTY USA/EU, mesmo Fable-2-Recomp (submódulo `a4b0274e67d82514d44b42ac9320c30dc93bdaa3`).
**ReXGlue SDK:** `3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b`.
**Conteúdo privado:** `default.xex` e `Fable2-Cpp-Real-Gerado-PRIVADO-24.zip`.

## 1) Aplicar a correção pública ao Fteste (pode ser pelo Termux)

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-compilar-Fable2-ARM64-25.zip -d .
python3 scripts/enable_fable2_private_arm64.py
python3 scripts/enable_fable2_private_arm64.py --check
python3 -m unittest discover -s tests -v

git add scripts/import_fable2_guest_cpp_private.py \
  scripts/enable_fable2_private_arm64.py scripts/build_android_native.sh \
  tests/test_fable2_private_arm64_25.py docs/FABLE2-PRIVATE-ARM64-25.md CHANGELOG-25.md
git commit -m "Preparar compilacao privada do Fable II ARM64"
git push origin main
```

**Não faça** `git add -f build/` nem adicione ZIPs do jogo.

## 2) Executar em Linux x86-64 (PC próprio ou VM privada)

É necessário um **Linux x86-64**, com `git`, Python 3, CMake, Ninja e o Android SDK/NDK. Não tente executar o gerador x86-64 diretamente no Termux ARM64. O NDK precisa conter `build/cmake/android.toolchain.cmake`, `toolchains/llvm/prebuilt/linux-x86_64` e `llvm-readelf`. Sugestão: NDK r27c / 27.2.12479018 e SDK Android com build-tools instalados.

Na sua máquina Linux, coloque **somente localmente**, fora do repositório:

```text
~/Fable2-private/default.xex
~/Downloads/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip
```

Baixe o repositório atualizado e suas dependências públicas:

```bash
git clone --recurse-submodules https://github.com/NanaveONE/Fteste.git
cd Fteste
bash scripts/setup_gpu_dependencies.sh
```

Se já tiver o checkout, use `git pull --ff-only` e `git submodule update --init --recursive`.

Configure caminhos **do seu ambiente** (modifique `ANDROID_NDK_HOME` para onde instalou o NDK):

```bash
export ANDROID_NDK_HOME="$HOME/Android/Sdk/ndk/27.2.12479018"
export REXSDK_DIR="$PWD/build/deps/rexglue-xerenge"
export FABLE2_GAME_ROOT="$HOME/Fable2-private"
export FABLE2_PRIVATE_CPP_ZIP="$HOME/Downloads/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip"
export BUILD_JOBS=2
```

O instalador **não precisa da pasta `data/` completa para compilar** o código já recompilado. Essa pasta será obrigatória para executar o Fable II no Android. **Não execute esse build em GitHub Actions público** com material privado.

Confira se o ReXGlue SDK local está na revisão esperada:

```bash
git -C "$REXSDK_DIR" rev-parse HEAD
# Esperado: 3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b
```

Se sua revisão não corresponde, faça um checkout limpo/compatível do SDK antes da compilação; não misture revisões ou patches locais sem conferir.

Execute a compilação do jogo:

```bash
bash scripts/build_android_native.sh 2>&1 | tee "$HOME/fable2-arm64-build.log"
```

O script faz: preparação isolada do Fable-2-Recomp; importação validada dos 297 `.cpp`; CMake com Android NDK e `libfable2.so`; verificação ELF ARM64, alinhamento 16 KB e símbolo exportado `SDL_main`.

**Resultado esperado se o build passar:**

```text
Fteste/build/fable2-android-arm64/libfable2.so
Fteste/build/fable2-guest-arm64-alignment.json
```

Quando houver erro de compilação ou linkagem, guarde **somente o log filtrado** (sem conteúdos extraídos do jogo) para diagnóstico. Revise o log antes de compartilhá-lo, pois ele pode conter caminhos privados.

## 3) O que acontece depois do `libfable2.so`

1. Conferir símbolos ABI com `librexruntime.so` ARM64, com a mesma revisão de SDK.
2. Concluir shader translation (16 pendências anteriores) e compilar `librexgpu-plume.so` para Fable II.
3. Estagiar as bibliotecas ARM64 e gerar o APK usando o pipeline já existente do Fteste.
4. Importar os dados originais da sua ISO no Android e testar execução/controles/áudio/Vulkan/salvamento no aparelho.

**Limites:** build de um `.so` não prova execução. O launcher e o jogo continuam bloqueados se o plugin ou shaders necessários estiverem ausentes.
