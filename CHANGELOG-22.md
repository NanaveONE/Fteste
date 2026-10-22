# Correcao 22 — Clang 19 / `std::expected` no Codegen Linux

**Log analisado:** `logs_108057232886.zip`, job `codegen-linux`, etapa 729/839.

## Erro comprovado

A compilacao com `/usr/bin/clang++` do Ubuntu 24.04 (Clang 18), embora com
`-std=c++23`, falhou em `include/rex/system/map_parser.h` e
`src/system/map_parser.cpp`: `std::expected` e `std::unexpected` indisponiveis.
A biblioteca GNU condiciona esses tipos a `__cpp_concepts >= 202002L`;
Clang 19 corrigiu esse sinalizador. Referencias:
- https://releases.llvm.org/19.1.0/tools/clang/docs/ReleaseNotes.html
- https://gcc.gnu.org/onlinedocs/gcc-13.1.0/libstdc%2B%2B/api/a00083_source.html
- https://packages.ubuntu.com/noble/amd64/clang-19

## Alteracoes

1. Instala `clang-19` e `libstdc++-13-dev` no Ubuntu 24.04 sem remover as
   dependencias SDL3/X11 corrigidas no patch 21.
2. Configura explicitamente `CMAKE_C_COMPILER=/usr/bin/clang-19` e
   `CMAKE_CXX_COMPILER=/usr/bin/clang++-19` no preset do Codegen.
3. Confirma no `CMakeCache.txt` que o compilador nao voltou para o Clang antigo.
4. Novo `scripts/check_fable_codegen_cpp23.py`: compila, vincula e executa um
   exemplo real que cobre `std::expected`, `std::unexpected`, `std::jthread` e
   `std::from_chars(float)` **antes** de iniciar a compilacao das 839 etapas.
5. Aplica a mesma protecao ao `scripts/build_host_tools.sh` para builds
   privados. Corrige ali a busca do binario gerado, que antes procurava
   somente sob `sdk/out/build/...` embora o CMake configure a saida em
   `sdk/out/linux-amd64/Release/rexglue`.
6. Testes unitarios com erro para compilador ausente/versao 18 e regressao dos
   caminhos de saida, do YAML e do Bash.

## Limites

Validado localmente o script, sua sintaxe e testes; **o Clang 19 do GitHub
Actions e o build ReXGlue completo ainda nao foram executados neste ambiente**.
O primeiro erro fatal comprovado foi `std::expected`; os avisos JACK, PipeWire,
libdecor, libusb e outros no log sao verificacoes opcionais do SDL3, nao novos
bloqueios comprovados. Se o link/empacotamento falhar apos esta correcao, usar o
novo log para ajustar apenas o ponto de falha real.

O workflow usa exclusivamente codigo aberto. Arquivos do Fable II, ISO,
`default.xex`, `data/`, caches privados e codigo C++ do jogo nao sao enviados.
