# Fable II Android — MemExport 51: cinco shaders experimentais SPIR-V

## Resultado verificado localmente

- Os **cinco** shaders HLSL da release privada do diagnóstico 43 compilaram com a **libdxcompiler.so real** proveniente do seu XenosRecomp.
- Há instruções de escrita em buffers SPIR-V e bindings **set0/binding8** (guest memory) e **set0/binding9** (16 bytes de contadores).
- O código **não usa Int64**, evitando exigir a capability `shaderInt64` dos aparelhos Android.
- 7 testes Python passaram. Foram verificados os hashes SHA-256 originais de cada HLSL.
- A versão dos cinco shaders **é experimental**, **não** foi adicionada ao cache de produção. O cache de produção continua **583/588** enquanto a integração real não está pronta.

**Limitações que impedem considerar os cinco shaders como corretos em runtime:**
1. Apenas stream **ColorFormat 38 = RGBA32_FLOAT**, número float 7, endian 0 e sem troca de canais é escrito; demais formatos incrementam o contador de erro no buffer 9. Não há conversão de 8/16 bits.
2. A transformação atual deduz índices `eM0..eM4` por ordem das escritas no HLSL do diagnóstico; ainda precisa validar máscaras, predicação e instruções `alloc/serialize` contra o microcódigo Xenos.
3. O Plume ainda precisa implementar **dois descritores SSBO** (set 0, bindings 8 e 9), storage real da memória convidada, isolamento de snapshots e callbacks da memória do jogo.
4. Verificar `vertexPipelineStoresAndAtomics` na GPU e implementar fallback compute se ausente.
5. Garantir barreiras `VERTEX_SHADER/SHADER_WRITE -> TRANSFER/TRANSFER_READ -> HOST/HOST_READ` e fence antes de copiar dados à RAM convidada, incluindo invalidação de memória mapeada não coerente e `MemoryWriter` 47/49/50.
6. **Não instalar o ZIP de shaders privados no GitHub público.** O workflow 51 privado, se usado, escreve só na release privada.

## Arquivos disponibilizados

- `Fteste-MemExport-51-Codigo-PUBLICO.zip` contém scripts e testes públicos. Pode ir ao repositório `Fteste`.
- `Fable2-MemExport-51-PRIVADO.zip` contém os HLSL derivados do jogo e cinco SPIR-V experimentais. **Deve ficar apenas na release `NanaveONE/Fable2-Arquivos-Privados`, nunca no Fteste público.**

## Termux — instalar apenas o código público

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-51-Codigo-PUBLICO.zip -d .
python3 -m unittest discover -s tests -p test_memexport_51.py -v
git add scripts/compile_memexport_51.py scripts/verify_spirv_memexport_51.py \
  scripts/dxc_spirv51.cpp tests/test_memexport_51.py \
  .github/workflows/test-fable-memexport51.yml \
  .github/workflows/build-fable-memexport51-private.yml INSTRUCOES-51.md
git commit -m "Traduzir cinco shaders MemExport experimentais 51"
git push origin main
```

Como o ZIP **privado** já foi compilado nesta conversa, salve-o em Downloads e faça upload **somente para o repositório privado**, sem precisar executar outro build público:

```bash
gh release upload guest-input-26 \
  ~/storage/downloads/Fable2-MemExport-51-PRIVADO.zip \
  --repo NanaveONE/Fable2-Arquivos-Privados --clobber
```

Alternativamente, o workflow privado pode reproduzir o experimento usando seu artefato compilado anteriormente:

```bash
gh workflow run build-fable-memexport51-private.yml \
  --repo NanaveONE/Fteste --ref main \
  -f release_tag=guest-input-26 -f xenos_run_id=39986495904
```

**Não execute o compilador final de GPU como se já houvesse 588 shaders válidos; o runtime ainda não implementa os buffers MemExport.**
