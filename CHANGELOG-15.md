# Correção 15 — ReXGlue Android ARM64: `std::from_chars(float)` no NDK r27

## Erro comprovado

Arquivo analisado: `logs_107996780799.zip`, workflow **android-runtime**, execução de 22/10/2026.

A correção 14 do SDK Manager funcionou. O CI instalou NDK **27.2.12479018**, baixou
`shipa-2/rexglue-xerenge` e chegou à etapa **452/678** do build `rexruntime`.

O Clang Android API 31 abortou a compilação de
`src/filesystem/CMakeFiles/rexfilesystem.dir/cmake_pch.hxx.pch` devido a três
instanciações sem sobrecarga viável de `std::from_chars` para `float`/`double`
em `include/rex/string/numeric.h` (linhas 195 e 322 no upstream analisado).

## Solução implementada

O fork já contém `portable_float_from_chars` para macOS, com parse de ponto
flutuante pela locale C usando `newlocale()`, `strtof_l()` e `strtod_l()`.
O Android API 31 também disponibiliza essas funções, mas sua libc++ r27 não
oferece o `std::from_chars` de ponto flutuante utilizado nesse cabeçalho.

- `scripts/patch_android_float_from_chars.py` ativa **a implementação existente**
  também para `__ANDROID__`, substituindo os quatro guards `#if REX_PLATFORM_MAC`
  por `#if REX_PLATFORM_MAC || defined(__ANDROID__)` em uma cópia privada de
  `include/rex/string/numeric.h`.
- Falha explicitamente se qualquer âncora upstream mudar ou se o cabeçalho já
  estiver parcialmente modificado; execuções repetidas não duplicam a mudança.
- `scripts/build_rexglue_android_sdk.sh` chama o patch e `--check` **antes**
  do CMake. Não mexe em `external/`, arquivos de jogo ou submódulos Git.
- `tests/test_android_float_charconv_15.py` inclui 5 testes, entre eles um
  programa C++ real compilado e executado com a implementação de conversão.

## Aplicação no Termux

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-ReXGlue-ARM64-15.zip -d .
python -m unittest discover -s tests -v
bash -n scripts/build_rexglue_android_sdk.sh
git add scripts/patch_android_float_from_chars.py \
        scripts/build_rexglue_android_sdk.sh \
        tests/test_android_float_charconv_15.py CHANGELOG-15.md
git commit -m "Corrigir from_chars float no ReXGlue Android NDK"
git push origin main
```

Depois execute [Compilar ReXGlue Android ARM64 (sem dados do jogo)](https://github.com/NanaveONE/Fteste/actions/workflows/build-android-runtime.yml).

## Validação e limites

- Testes: **5 novos testes passaram localmente**; sintaxe Bash validada.
- Funções bionic _l são disponíveis a partir do Android API 26 e `newlocale`
  desde API 21; o workflow utiliza API 31.
- **Build ARM64 completo NÃO foi executado aqui**, pois o NDK Android não está
  instalado no ambiente local. O próximo workflow pode revelar outras falhas
  independentes; não é prova de APK jogável, áudio, shaders ou EDRAM.
