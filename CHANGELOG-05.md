# Fable II Android — Integração 05: codegen obrigatório + SDK/ELF auditado

**Estado:** pipeline mais confiável para construção real, **não há APK jogável**.

## Problema identificado e correção

A implementação Fable-2-Recomp tem uma sutileza importante: `generated/rexglue.cmake`
carrega `generated/default/sources.cmake` **durante a configuração do CMake**.
Se `cmake` iniciar antes que exista um índice de código gerado, o alvo
`fable_2_recomp` não é criado. Assim seria possível tentar compilar uma lib
sem o código recompilado do Fable II. A integração 05 agora:

1. Executa `FABLE2_CODEGEN_TOOL codegen` **antes** do CMake Android, numa cópia
   local do repositório Fable (sem modificar o submódulo original).
2. Impede uma configuração Android sem `sources.cmake` e sem `fable_2_recomp`.
3. Exige `POSITION_INDEPENDENT_CODE` para ligar os objetos PPC recompilados
   à biblioteca compartilhada `libfable2.so`.
4. Rejeita misturar outro `default.xex` na mesma cópia de trabalho.
5. `scripts/audit_android_sdk.py` verifica requisitos específicos do SDK
   Android, incluindo entrada `SDL_main`, suporte à memória/fibras e interface
   pública de GPU. Compara a versão da ABI quando o SDK original estiver disponível.
6. `scripts/stage_android_libs.py` coleta as dependências **reais** `DT_NEEDED`
   da lib de jogo, runtime e renderizador, impede misturar .so com nomes
   duplicados/arquitetura errada e recusa referências a Burnout. Só produz
   `build/android-native-stage/` se todas as verificações de ELF passarem.
7. A CI agora testa o fluxo, sem fingir compilar o jogo sem dados legítimos.

## Executar a etapa de verificação

No Termux é possível conferir os fontes:

```bash
cd ~/Fteste
git pull
git submodule update --init --recursive
python -m unittest discover -s tests -v
python scripts/verify_port_layout.py
```

No Linux com Android NDK, as fontes de Fable II e Xerenge e uma cópia pessoal
compatível de Fable II, antes da tentativa de compilação:

```bash
export ANDROID_NDK_HOME=/seu/sdk/ndk/versao
export REXSDK_DIR="$PWD/build/deps/rexglue-xerenge"
export FABLE2_CODEGEN_TOOL=/caminho/para/rexglue-compilado-para-o-PC
export FABLE2_GAME_ROOT=/caminho/privado/para/Fable2-extraido
export PLUME_ROOT="$PWD/build/deps/plume-xerenge"
export XENOS_RECOMP_ROOT="$PWD/build/deps/XenosRecomp-xerenge"
python3 scripts/audit_android_sdk.py --sdk "$REXSDK_DIR"
bash scripts/build_android_native.sh
bash scripts/build_fable_gpu.sh
```

`build_android_native.sh` **pode falhar** por incompatibilidade entre as duas
forks do ReXGlue, codegen e funções Win32 no Fable II. Isso deve ser corrigido
caso a caso com logs de compilação; uma aprovação dos testes Python não substitui
um compilador Android. Do mesmo modo, o plugin Plume compilado ainda requer
compatibilidade real com os comandos gráficos e shaders de Fable II.

### Montar bibliotecas para o APK (apenas depois de compilar)

```bash
python3 scripts/stage_android_libs.py \
  --game-lib build/fable2-android-arm64/libfable2.so \
  --gpu-lib build/fable2-gpu-android-arm64/librexgpu-plume.so \
  --runtime-lib /caminho/para/librexruntime.so \
  --cxx-lib "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so" \
  --search-dir /pasta/que-contem-outras-bibliotecas-Android \
  --readelf "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
```

Se forem exigidas bibliotecas acessadas por `dlopen` (como hooks do
libadrenotools), forneça cada arquivo necessário com `--extra-lib caminho.so`.
A inspeção de `DT_NEEDED` **não** encontra dependências carregadas só via
`dlopen` ou nomes de plugin criados dinamicamente.

Somente após uma preparação bem-sucedida:

```bash
export NATIVE_LIB_DIR="$PWD/build/android-native-stage"
export SDL_JAVA_DIR=/pasta/das/fontes/Java/SDL3
export ANDROID_HOME=/seu/sdk
bash scripts/package_android_apk.sh
```

## Testes e limites

Os testes Python e sintaxe shell são verificações **locais** de fontes e fluxo,
não uma compilação do código do Xbox 360 nem uma validação da ABI C++ de ponta
a ponta. A maior lacuna continua sendo o suporte de shaders construídos durante
a execução, EDRAM, resolves e formatos/estados usados por Fable II.

**Nenhum arquivo do jogo ou código recompilado proprietário é distribuído.**
O port de Plume reutiliza código GPL do Xerenge: preservar atribuição e licença.
