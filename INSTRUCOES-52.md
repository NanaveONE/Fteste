# Fable II — MemExport 52: buffers Vulkan reais nos bindings 8 e 9

## Feito

- Plume `set=0, binding=8` passa a ter um `VK_DESCRIPTOR_TYPE_STORAGE_BUFFER` real.
- Plume `set=0, binding=9` passa a ter outro buffer real para os 3 contadores de shader51.
- A API `addReadWriteByteAddressBuffer` é a API original de `plume-xerenge` (não é simulada).
- `ReadbackBuffer` do Plume usa memoria **HOST_COHERENT** na implementação Vulkan existente.
- Os contadores são zerados antes do envio GPU e lidos após o `ClearAndPresent` síncrono,
  que espera o fence da submissão. O modo `XERENGE_ASYNC_PRESENT` é rejeitado quando a
  sonda está ativada. A feature `vertexPipelineStoresAndAtomics` é consultada no driver.
- Recursos e descritores são destruídos na rotina `Shutdown()`.
- `apply_fable_plume52.py` usa apenas overlay separado e verifica hashes de conteúdo.

## Importante — não é jogo jogável

`FABLE2_MEMEXPORT52_PROBE=1` é experimental: aloca 64 MiB de buffer de
armazenamento host-coerente, cobre apenas endereços nesse intervalo e **não
copia** os dados da GPU para a RAM convidada, porque o shader51 não produz
um registro confiável dos endereços tocados. Portanto não há commit host,
nenhum suposto sucesso de jogo, nem alteração automática de 583/588 para 588.
A compilação do `librexgpu-plume.so` ainda depende do cache 100% válido e
segue bloqueada pela validação existente. Necessário: criar journal
GPU dos endereços e reunir a exclusão/sincronização da memória convidada.

## Termux

Baixe `Fteste-MemExport-52-Plume-Vulkan.zip` e rode:

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-52-Plume-Vulkan.zip -d .
python3 -m unittest discover -s tests -p test_memexport52.py -v
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_memexport52.cpp -o "$HOME/test-fable52"
"$HOME/test-fable52"
python3 scripts/install_fable_plume52.py --root .
python3 scripts/install_fable_plume52.py --root . --check
bash -n scripts/build_fable_gpu.sh

git add scripts/apply_fable_plume52.py scripts/install_fable_plume52.py \
  scripts/build_fable_gpu.sh port/gpu/fable_memexport52.h \
  tests/test_memexport52.py tests/test_fable_memexport52.cpp \
  .github/workflows/test-fable-memexport52.yml INSTRUCOES-52.md
git commit -m "Ligar Vulkan SSBO MemExport bindings 8 e 9 (52)"
git push origin main
```

Não enviar shaders HLSL/SPIR-V ou `default.xex` para este repositório público.
Não rerodar o build `libfable2.so`.
