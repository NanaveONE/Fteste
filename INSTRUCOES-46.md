# Plume 46 — Vulkan loop constants: binding 7 e snapshots reais

Este é um patch **real, mas PARCIAL**, para o GPU Plume do Fable II. Ele fecha a lacuna de conexão dos registradores de loop (`i0`, `i16` etc.) da correção 42. **Não implementa ainda MemExport eM/eA na GPU, nem faz os cinco shaders faltantes compilar.** A situação continua **583/588**; não existe APK jogável certificado.

## Funcionalidade implementada

- Captura os 32 registradores reais SQ_LOOP (`gpu_registers_[0x4908..0x4927]`) em cada snapshot, sem reutilizar dados incorretos entre draws.
- Descompacta contagem/valor inicial/passo assinado (o byte do passo possui sinal) em `int4[32]` = 512 bytes e preserva a palavra original em `w`.
- Cria um uniform buffer dinâmico para a tabela, 16384 slots de 512 bytes (dois conjuntos de 8192 por frame) para evitar sobrescrever dados de draws em voo.
- Acrescenta **set=0/binding=7**, mantém os descritores 0 a 6 intactos, fornece o quarto offset dinâmico ao Vulkan via Plume.
- Trabalha **somente no overlay local** dos fontes Xerenge. Não modifica o clone upstream, nem o `libfable2.so`.
- Garante falha explícita se a versão dos fontes divergir dos pontos de inserção esperados. Testes C++/Python são executáveis sem arquivos privados.

## Instalar no Termux

Após baixar `Fteste-Plume-MemExport-46.zip`:

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-Plume-MemExport-46.zip -d .
python3 -m unittest discover -s tests -p 'test_*plume46.py' -v
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_plume46.cpp -o /tmp/plume46-test
/tmp/plume46-test
python3 scripts/install_fable_plume46.py --root .
bash -n scripts/build_fable_gpu.sh
```

O comando `install_fable_plume46.py` atualiza SOMENTE `scripts/build_fable_gpu.sh` e `port/gpu/CMakeLists.txt` do Fteste. Ele **não** cria ou altera o overlay até que `build_fable_gpu.sh` seja chamado futuramente com as dependências instaladas. O overlay 46 é separado do `fable2-plume-overlay-v2`, que permanece verificável e intocado.

```bash
git add scripts/apply_fable_plume46.py \
  scripts/install_fable_plume46.py \
  scripts/build_fable_gpu.sh \
  port/gpu/CMakeLists.txt \
  port/gpu/fable_loop_constants_46.h \
  tests/test_fable_plume46.cpp \
  tests/test_apply_plume46.py \
  tests/test_install_plume46.py \
  .github/workflows/test-fable-plume46.yml \
  INSTRUCOES-46.md
git commit -m 'Integrar constantes SQ loop do Xenos ao Plume Vulkan binding7'
git push origin main
```

O GitHub Actions `test-fable-plume46.yml` testará a integração dos scripts. **Não rode o build de shader 40 ou o build GPU agora:** o primeiro ainda bloqueará os 5 shaders MemExport e o segundo exige cache SPIR-V 100%.

## Validações já executadas (fora do Android)

- Testes de decodificação do loop bank com `clang++` (valores sintéticos; conta, início e passo negativo).
- 8 testes unitários Python de falha segura, instalação e anchors.
- Âncoras principais do overlay conferidas no `shipa-2/Xerenge` público.

**Ainda não testado:** compilação Android NDK do Plume com o overlay 46, execução Vulkan no celular, pipeline real da Fable II, valores de SQ_LOOP fornecidos pelo jogo em tempo real.

## Para concluir o MemExport (próximas mudanças obrigatórias)

- XenosRecomp: `eA` define endereço/stream, `eM0..4` escreve valores, com máscaras, predicação e `alloc export`/flush. Não converter eA/eM em saída de posição.
- GPU Vulkan: suporte opcional `vertexPipelineStoresAndAtomics` ou compute fallback; storage buffers de memória convidada com codificação precisa do formato, endianness e swap de componentes.
- Barreiras Vulkan apropriadas após escrita e readback/invalidations da memória CPU. MemExport pode alimentar novos buffers de vértices, e não apenas efeitos visuais.
- Religar geração dos cinco shaders e rodar testes de equivalência/validação em GPU até 588/588 (sem enfraquecer a cobertura).

A implementação completa requer essas etapas; compilação HLSL sozinha **não** garante que a memória será escrita corretamente.
