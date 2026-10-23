# MemExport 50 — ponte validada para readback Vulkan

Adiciona uma ponte C++ à API existente do MemExport 49. O renderizador tem que:
(1) produzir as escritas reais de eA/eM por shader GPU/compute; (2) colocar
barreiras GPU->TRANSFER, realizar cópia para staging legível; (3) aguardar
`vkWaitForFences`; (4) chamar `vkInvalidateMappedMemoryRanges` quando o
staging não for HOST_COHERENT; (5) converter bytes do formato Xbox 360;
(6) adquirir acesso exclusivo à RAM convidada e chamar a ponte.

A ponte recusa dados não convertidos, falta de fence, falta de invalidação,
reuso e exportações fora dos limites. Não conecta o backend à execução real
porque os requisitos (1)-(5) ainda não existem no Plume Fable II.

## Testar no Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-50.zip -d .
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_memexport_vulkan50.cpp -o "$HOME/test-fable50"
"$HOME/test-fable50"
git add port/gpu/fable_memexport_vulkan50.h tests/test_fable_memexport_vulkan50.cpp \
  .github/workflows/test-fable-memexport50.yml INSTRUCOES-50.md
git commit -m 'MemExport 50: contrato seguro de readback Vulkan'
git push origin main
```

**Não é GPU Vulkan funcional, nem resolve os cinco shaders faltantes!**
A exigência 588/588 permanece, com 583 shaders compilados. Não mexe no
`libfable2.so`; não inclui conteúdo comercial do jogo.
