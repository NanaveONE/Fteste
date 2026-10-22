# Correcao 21: Linux ReXGlue Codegen SDL3/X11

## Falha comprovada

Log `logs_108052749143.zip` (22/10/2026), workflow `build-fable-codegen-host.yml`:

```
CMake Error at thirdparty/sdl3/cmake/macros.cmake:433:
  Couldn't find dependency package for XSCRNSAVER.
  Please install the needed packages or configure with -DSDL_X11_XSCRNSAVER=OFF
```

A configuração do SDL3 habilitava X11, mas o runner Ubuntu 24.04
não tinha os arquivos de desenvolvimento XScreenSaver (`libxss-dev`).
A compilação não começou: falhou na etapa `cmake --preset`.

## Mudanças

* Inclui `libxss-dev` para resolver o erro observado.
* Inclui `libxtst-dev`, `libxfixes-dev`, `libxrender-dev` e outros
  headers de extensões X11 para prevenir novas falhas nos próximos
  `CheckX11()` da versão SDL3 utilizada pelo fork.
* Faz preflight dos headers XScreenSaver/XTest e de `x11-xcb`,
  `wayland-client`, `xkbcommon` antes de invocar CMake.
* Mantém a compilação do `rexglue` Linux x86_64 em Release e a inspeção
  do ELF, dependências e `--version`/`codegen --help`.
* Inclui seis testes de regressão, sem dados do jogo.

Referência: https://wiki.libsdl.org/SDL3/README-linux

## Limites

Não foi executado o GitHub Actions Ubuntu 24.04 neste ambiente.
Os testes locais verificam sintaxe e preparação de dependências,
não a compilação do SDK completo. Avisos `jack`, `pipewire`, `sndio`
no log anterior eram opcionais, não a causa fatal.

Quando o gerador for compilado, a geração real do código do Fable II
deve acontecer num ambiente privado, utilizando a cópia do jogo do usuário.
Nunca inclua dumps, `default.xex`, fontes gerados ou caches privados no
repositório público ou no artefato GitHub Actions.
