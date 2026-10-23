# Fable II Android — Correção 55: contrato de escrita física MemExport

## Propósito

Esta correção inclui uma implementação C++ real da **transação de escrita**
para o journal MemExport 53, com preflight total dos destinos, conversão de
words de 32 bits condicionada a semântica Xenos comprovada, notificação dirty,
e RAII para liberar um bloqueio de threads mesmo em falhas.

**ATENÇÃO: O SDK Plume/ReXGlue utilizado NÃO tem ainda um provedor certificado de
parada global de todas as threads convidadas instalado. O ponteiro
`memexport55_host_` começa `nullptr` e a versão 55 continua sem modificar
memória de jogo por padrão.** Não confunda testes em RAM simulada com uma
execução Android real. Não ative ou simule `AcquireGlobalGuestExclusion()`.

## Uso no Termux

```sh
cd ~/Fteste
unzip -o "$HOME/storage/downloads/Fteste-MemExport-55-Guest-RAM.zip" -d .
python3 -m unittest discover -s tests -p test_memexport55.py -v
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic tests/test_memexport55.cpp -o "$HOME/test-fable55"
"$HOME/test-fable55"
python3 scripts/upgrade_fable55_ci.py --root .
python3 scripts/install_fable_plume55.py --root .
python3 scripts/upgrade_fable55_ci.py --root . --check
python3 scripts/install_fable_plume55.py --root . --check
python3 scripts/install_fable_plume52.py --root . --check
python3 scripts/install_fable_plume53.py --root . --check
bash -n scripts/build_fable_gpu.sh
```

Em seguida:

```sh
git add scripts/apply_fable_plume55.py scripts/install_fable_plume55.py \
  scripts/upgrade_fable55_ci.py scripts/install_fable_plume52.py \
  scripts/install_fable_plume53.py scripts/build_fable_gpu.sh \
  port/gpu/fable_memexport_guest55.h tests/test_memexport55.cpp \
  tests/test_memexport55.py .github/workflows/test-fable-memexport55.yml \
  INSTRUCOES-55.md
git commit -m "Adicionar transacao MemExport 55 com parada global obrigatoria"
git push origin main
```

## O que a biblioteca valida

- GPU fence concluído e buffer legível (flags só podem vir do backend real).
- Journal 53 íntegro, sem overflow, formato/endianness confirmados e sem sobreposição.
- Todos os endereços físicos traduzidos e mapeados sob exclusão, **antes** de
  escrever o primeiro byte; falha em qualquer um aborta o lote inteiro.
- 4x32 bits convertidos em BE/LE somente conforme decisão explicitamente
  certificada pelo backend (o modo padrão é `Unknown`, recusado).
- Notificações dirty são enviadas ainda sob exclusão; RAII garante release.

## Bloqueadores remanescentes

1. Integrar um provedor do SDK que realmente consiga pausar globalmente os
   threads guest sem deadlocks e emitir dirty/invalidation, com provas em dispositivo.
2. Provar a interpretação das flags Xenos MemExport e endian dos cinco shaders.
3. Validar que todos os patches sobre Xerenge compilam no NDK ARM64 e que
   `librexgpu-plume.so` executa com o hardware Vulkan real.
4. Somente após os itens anteriores, considerar os cinco shaders no cache
   de produção — este continua em **583/588**.

Não colocar arquivos do jogo nem HLSL/SPIR-V proprietários em `Fteste`.
`libfable2.so` compilado não é alterado.
