# Integração 17 — correção da descoberta de `librexruntime.so` e auditoria de dependências

## Evidência retirada de `logs_108017934576.zip`

O GitHub Actions compilou o runtime do ReXGlue para Android ARM64 sem erro fatal de compilação/linkagem. O trecho final do log é:

```text
[677/678] Linking CXX shared library .../build/deps/rexglue-xerenge/out/android-arm64/librexruntime.so
BLOCKED: expected one ARM64 librexruntime.so, found 0
```

A origem é confirmada no `CMakeLists.txt` do fork `shipa-2/rexglue-xerenge`: ele configura
`CMAKE_LIBRARY_OUTPUT_DIRECTORY` em `${REXGLUE_ROOT}/out/${REX_PLATFORM}`. O
script antigo procurava somente em `build/rexglue-android-arm64` (diretório `-B`),
que **não é** a saída configurada pelo CMake.

Os avisos de parâmetros não utilizados, `missing field initializer`, pragmas etc.
são avisos, **não** erros fatais. As verificações `Looking for ... not found`
registradas pelo CMake são sondagens opcionais de plataforma, não interrupções.

## Correções efetivas

1. `scripts/build_rexglue_android_sdk.sh`: após o CMake, invoca um empacotador
   verificável em vez de procurar `librexruntime.so` na pasta errada. Entrega a
   localização estável `build/artifacts/rexglue-android-arm64/librexruntime.so`.
   **Mantém todos os patches anteriores de áudio, `from_chars` e timer.**
2. `scripts/package_rexruntime_arm64.py`: identifica a saída real do SDK ou
   fallback documentado, rejeita caminhos divergentes, verifica cabeçalho ELF
   (ELF64, little-endian, AArch64, `ET_DYN`), valida `DT_SONAME` e coleta o
   fechamento recursivo das dependências dinâmicas `DT_NEEDED`. Busca bibliotecas
   somente na saída **da mesma build Android** e no `libc++_shared.so` do NDK;
   rejeita bibliotecas ausentes, erradas e divergentes. Copia transacionalmente,
   confere SHA-256 e produz `runtime-build-report.json`. Não assume que o
   `SDL_main` é fornecido pelo runtime — pode estar na biblioteca do jogo.
3. `.github/workflows/build-android-runtime.yml`: o upload agora aponta para
   a pasta **real** `build/artifacts/rexglue-android-arm64/` e exige seu relatório.
4. `scripts/attempt_playable_build.sh`: deixa de procurar `librexruntime.so`
   no diretório `-B`, utiliza o runtime já verificado e passa automaticamente
   sua pasta como `--search-dir` a `stage_android_libs.py`. Isso evita perda
   de dependências como `libSDL3.so` no empacotamento posterior.
5. `tests/test_android_runtime_artifact_17.py`: casos de saída do SDK versus
   `-B`, dependências transitivas, biblioteca ausente, arquitetura incorreta,
   duplicatas, resíduos de build e integração com o workflow.

## Validações feitas

- 8 testes novos passaram com artefatos ELF **sintéticos**, incluindo um
  `llvm-readelf` simulado apenas no teste.
- Scripts de shell passam em `bash -n`.
- Workflow YAML foi analisado sem erros.
- Fonte CMake e log Android originais conferidos.

**Não foi possível executar um NDK Android completo neste ambiente**; o usuário
precisa rodar novamente o workflow manual após aplicar o patch. Os testes
sintéticos não são apresentados como um `librexruntime.so` real compilado.

## Passos

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-ReXGlue-ARM64-17.zip -d .
python -m unittest discover -s tests -v
bash -n scripts/build_rexglue_android_sdk.sh scripts/attempt_playable_build.sh

git add .github/workflows/build-android-runtime.yml \
  scripts/build_rexglue_android_sdk.sh \
  scripts/package_rexruntime_arm64.py \
  scripts/attempt_playable_build.sh \
  tests/test_android_runtime_artifact_17.py CHANGELOG-17.md
git commit -m "Corrigir runtime ARM64 e dependencias Android 17"
git push origin main
```

Execute **Compilar ReXGlue Android ARM64 (sem dados do jogo)** em
`https://github.com/NanaveONE/Fteste/actions/workflows/build-android-runtime.yml`.
Se passar, baixe o artefato `rexglue-android-arm64-runtime-only`. Ele contém
somente bibliotecas nativas open-source necessárias ao runtime e um relatório;
não contém nem torna jogável o Fable II.

## Pendências não resolvidas por este patch

- `libfable2.so` exige compilação do código recompilado do jogo sob o mesmo SDK;
  o log deste workflow não contém esse build.
- O cache conhecido ainda contém 572/588 shaders convertidos; restam 16, de
  modo que `attempt_playable_build.sh` continuará **deliberadamente** bloqueado
  pela verificação de 100% até a correção de XenosRecomp.
- O plugin Plume/Vulkan e os comandos de EDRAM do Fable II não foram validados.
- Dependências SDL Java, áudio, saves, entrada e gameplay exigem a montagem
  final do APK e testes reais no aparelho.
- A validação ELF e de `DT_NEEDED` não garante correspondência de ABI C++ nem
  que o linker Android consiga carregar todos os símbolos em tempo de execução.

O estado correto é: **runtime Android compilado até a linkagem no CI**, mas
**ainda não verificado/empacotado com sucesso nesta revisão**.
