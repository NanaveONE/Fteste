# Fable II — Diagnóstico MemExport 44

**Status:** `BLOCKED_GPU_MEMEXPORT`. O material aqui NÃO faz compilação funcionar e não produz APK jogável.

## Resultado do diagnóstico 43 (SHA-256 dos cinco HLSL conferidos)

- 588 shaders extraídos de `Shaders.sbk` e `ShadersRelease.sbk`.
- 583 shaders traduzidos, 5 vertex shaders bloqueados (99,15% de cobertura).
- 23 marcadores de MemExport: 9 exports de endereço (`eA`) e 14 exports de dados (`eM#`).
- Os streams vêm de constantes da GPU. Os dois shaders maiores usam até 3 streams diferentes: posição, texcoord0 e normal.
- O arquivo `memexport-44-summary.json` contém somente informações técnicas de estrutura, **não** inclui os HLSL do jogo.

## Como usar

Para reproduzir o diagnóstico no Termux, **sem subir arquivos privados ao repositório público**:

```bash
cd ~/Fteste
python3 scripts/analyze_fable_memexport_44.py \
  --diagnostic ~/storage/downloads/Fable2-MemExport-DIAGNOSTICO-43.zip \
  --report ~/storage/downloads/fable2-memexport-44.json
```

Teste sintético (não requer o jogo):

```bash
python3 -m unittest discover -s tests -p 'test_memexport_44.py' -v
```

Para incluir somente o código analisador e seus testes no repositório público:

```bash
cd ~/Fteste
git add scripts/analyze_fable_memexport_44.py tests/test_memexport_44.py INSTRUCOES-44.md
git commit -m "Adicionar analise segura de MemExport Fable II 44"
git push origin main
```

O arquivo `memexport-44-summary.json` é um diagnóstico de metadados, não a tradução completa. **Não envie** para o repositório público o ZIP diagnóstico 43, nem os arquivos HLSL, o cache ou os `.sbk` originais.

## Implementação realmente necessária (XenosRecomp e Plume)

1. Traduzir separadamente os exports `eA` (índice 32) e `eM0..4` (33..37), incluindo mascaramento, predicação e mudanças de fluxo/stream. Não usar `output.oPos` para ambos.
2. Interpretar os 4 registradores do stream `xe_gpu_memexport_stream_t`, que codificam base física, quantidade de elementos, formato, endianness e ordenação de componentes. O segundo elemento não é simplesmente `base + 16`: depende do tamanho do formato.
3. Rejeitar endereços fora do segmento do jogo, mapear storage buffer para a memória convidada, implementar leitura de volta e sincronização de CPU/GPU (dependendo da estratégia de emulação).
4. Fazer fallback por compute shader quando Vulkan não oferecer `vertexPipelineStoresAndAtomics`, que não é obrigatório em todos os Androids.
5. Conectar o UBO de constantes inteiras em binding 7 introduzido pela correção 42, com os **valores reais** do jogo; não zerá-los.
6. Verificar os 5 shaders com testes de acesso a memória, e então recompilar o tradutor e conferir a cobertura 588/588 antes de tentar a `.so` da GPU.

Fontes técnicas públicas para a semântica, sem uso de material proprietário:
- https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/xenos.h
- https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/ucode.h
- https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/shader.h

### Nota importante

O ZIP 43 já mostra que o renderer não suporta MemExport nem o binding 7. Retirar o `#error` só fingiria sucesso na compilação; não corrigiria o jogo. Não execute novamente o workflow 40 com o mesmo tradutor até implementar o lado GPU.
