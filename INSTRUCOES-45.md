# MemExport 45 — decoder e planejamento seguro de escrita de memoria

**Implementado:** decodificacao dos registradores eA.xyzw do Xenos, tamanho
em bytes de formatos comuns e verificacao de destino eM0..eM4 no intervalo
de memoria convidada. Usa somente dados sintéticos e conceitos publicos de
`xenia-project/xenia/src/xenia/gpu/xenos.h`.

**Nao implementado:** shader translation dos 5 bloqueados, GPU storage buffer
Vulkan, packing final dos formatos, troca de endianness, sincronizacao GPU/CPU,
feature `vertexPipelineStoresAndAtomics`, ligacao do binding 7. Portanto nao
muda o resultado 583/588 nem produz APK jogavel. ESTE CODIGO NAO ESCREVE em RAM.

## Termux

Depois de baixar o ZIP, rode:

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-45.zip -d .
pkg install clang -y
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_memexport_45.cpp -o /tmp/test-fable-memexport-45
/tmp/test-fable-memexport-45
```

Para enviar apenas codigo PUBLICO e testes ao GitHub:

```bash
git add port/gpu/fable_memexport_45.h \
  tests/test_fable_memexport_45.cpp \
  .github/workflows/test-fable-memexport-45.yml \
  INSTRUCOES-45.md
git commit -m "Implementar decodificacao segura de MemExport 45"
git push origin main
```

O workflow `test-fable-memexport-45.yml` sera disparado no push. Nao precisa
reenviar SBK, HLSL, default.xex nem recompilar libfable2.so.

**Proximo passo de engenharia**: mapear o buffer de escrita do guest (conversao
de formato e sincronizacao), integrar com o pipeline Vulkan e depois implementar
exportacoes eA/eM no XenosRecomp. Use o codigo 45 como base testada para
enderecos, sem supor que tenha implementado essas operacoes graficas.
