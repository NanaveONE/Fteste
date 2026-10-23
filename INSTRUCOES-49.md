# Fable II MemExport 49 — sincronização segura CPU após readback

O estado real continua **583/588 SPIR-V**. Este pacote não implementa as instruções `eA/eM` no tradutor e não cria `librexgpu-plume.so`.

## Implementação

A nova classe C++ `ReadbackBatch` permite preparar os bytes **já convertidos**, impedir escrita antes de fence/invalidate GPU, exigir posse exclusiva da memória convidada, validar todos os destinos antes de copiar e publicar faixas alteradas para invalidação do cache do emulador. Reutiliza a implementação CPU da correção 47.

Ela não chama Vulkan: quem integrar o renderizador ainda deve implementar geração das escritas no shader, armazenamento no storage buffer, cópia de volta, espera pela fence `vkWaitForFences`, invalidação `vkInvalidateMappedMemoryRanges` nas alocações não coerentes, conversão Xenos endian/format e sincronização com threads do guest.

As duas flags booleanas de conclusão são um *contrato* de integração, **não** prova de que Vulkan sinalizou nada. Nunca chame `CompleteAfterFence(true, true)` sem esses dois resultados reais.

## Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-49.zip -d .
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_memexport_sync_49.cpp -o "$HOME/test-fable49"
"$HOME/test-fable49"
git add port/gpu/fable_memexport_sync_49.h \
  tests/test_fable_memexport_sync_49.cpp \
  .github/workflows/test-fable-memexport49.yml INSTRUCOES-49.md
git commit -m 'Criar handoff seguro MemExport GPU CPU 49'
git push origin main
```

O workflow público exercita somente testes sintéticos, sem publicar arquivos do jogo. Não reexecute o workflow de shaders 40: MemExport ainda precisa de implementação nos shaders e GPU.
