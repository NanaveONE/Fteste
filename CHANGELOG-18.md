# Fable II Android — Integração 18: runtime ARM64 confirmado e compatibilidade 16 KB

## Runtime real recebido e auditado — 22/10/2026

O usuário forneceu o artefato `rexglue-android-arm64-runtime-only.zip` produzido no GitHub Actions. Inspeção local de `librexruntime.so` e `libc++_shared.so` confirmou:

| Campo | `librexruntime.so` | `libc++_shared.so` |
|---|---|---|
| ELF | ELF64 little-endian, AArch64 `ET_DYN` | ELF64 little-endian, AArch64 `ET_DYN` |
| Tamanho | 94.027.864 bytes (inclui debug info) | 1.794.776 bytes |
| SHA-256 | `c794d649eb7e320a15f83b5da8300f57e15306bd0a122f47161b5a4ef1433195` | `f9992c4ba6b7c5a716e3a202fceb1ce029d6a2b0605838ac6b3219f489dd7970` |
| Menor alinhamento PT_LOAD | **4096 bytes** | **16384 bytes** |

A biblioteca foi compilada com Android NDK r27c / API 31 e o símbolo `rex::InitializeAndroidApp()` está exportado. O `SDL_main` NÃO é exportado pelo runtime; o ponto de entrada precisa existir na biblioteca do jogo antes do APK. As dependências DT_NEEDED são bibliotecas de sistema Android e `libc++_shared.so`, incluída no arquivo. Não foi detectada dependência `libSDL3.so` nesta build; não inventar bibliotecas extras para empacotar.

### Problema preventivo encontrado

O `librexruntime.so` real possui segmentos PT_LOAD com alinhamento de **4 KB**. Ele foi compilado corretamente para aparelhos com páginas de 4 KB, mas não atende os requisitos de carregamento de binários em aparelhos Android com páginas de **16 KB**. A `libc++_shared.so` do mesmo artefato já atende 16 KB.

O Android NDK r27 suporta a opção CMake `-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON`, que habilita alinhamento de 16 KB. A mesma opção deve ser usada no build de TODAS as bibliotecas AArch64 do jogo e do plugin, não apenas no runtime. Fonte: documentação oficial Android sobre páginas de 16 KB.

## Arquivos desta correção

- `scripts/check_android_16k_alignment.py`: lê diretamente os cabeçalhos de programa ELF, verifica arquitetura AArch64, integridade dos segmentos, alinhamento `PT_LOAD >= 16384` e opcionalmente gera relatório JSON. Não exige NDK nem faz afirmações sobre gameplay.
- `scripts/enable_android_16k.py`: patch de código-fonte determinístico/idempotente que altera 5 arquivos do repositório existente, preservando o restante das integrações. Confere todos os pontos antes de gravar qualquer arquivo.
- `tests/test_android_16k_alignment_18.py`: regressões com arquivos ELF sintéticos e testes de aplicação do patch. Nada de código/dados do jogo foi incluído no ZIP.

O patch aplica a opção do NDK nos builds de `librexruntime.so`, `libfable2.so` e `librexgpu-plume.so`, e adiciona inspeção do alinhamento no workflow do runtime e antes do empacotamento do APK.

## Aplicar e commitar (Termux)

```sh
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-alinhamento-ARM64-18.zip -d .
python scripts/enable_android_16k.py
python scripts/enable_android_16k.py --check
python -m unittest discover -s tests -v
bash -n scripts/build_rexglue_android_sdk.sh scripts/build_android_native.sh scripts/build_fable_gpu.sh scripts/package_android_apk.sh

git add scripts/check_android_16k_alignment.py scripts/enable_android_16k.py \
  scripts/build_rexglue_android_sdk.sh scripts/build_android_native.sh \
  scripts/build_fable_gpu.sh scripts/package_android_apk.sh \
  .github/workflows/build-android-runtime.yml \
  tests/test_android_16k_alignment_18.py CHANGELOG-18.md
git commit -m "Alinhar bibliotecas Fable II ARM64 a paginas Android de 16 KB"
git push origin main
```

Depois, o workflow manual **Compilar ReXGlue Android ARM64 (sem dados do jogo)** recompila um runtime novo com suporte a páginas de 16 KB. O **artefato atual permanece válido para páginas de 4 KB** e pode ser conservado. O workflow passará a recusar 4 KB devido à nova checagem.

## O que ainda não foi resolvido

- `libfable2.so` não foi compilado neste ambiente: código recompilado, XEX e demais `data/` privados e ferramentas de build precisam estar em Linux x86_64 com Android NDK.
- O cache de shaders estáticos conhecido contém 572/588 shaders; faltam 16 antes do build Vulkan pelo gate atual de 100%.
- Plume Vulkan / EDRAM / comandos gráficos e áudio, saves e gameplay ainda não estão validados em aparelho real.
- O alinhamento ELF de 16 KB NÃO resolve código nativo que assuma páginas fixas de 4096 bytes; testes em dispositivo de 16 KB ainda são necessários.

**Nenhum APK jogável é reivindicado nesta atualização.**
