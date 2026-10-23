# Fable II ARM64 — MemExport 53, diário real de escritas Vulkan

## Mudanças verificáveis

* Shaders experimentais 51 foram recompilados pelo DXC REAL para SPIR-V com novo `set=0,binding=10`. Cada escrita `RGBA32_FLOAT` tenta reservar atomicamente um slot no diário, grava o endereço físico e os quatro dwords do valor, com assinatura/complemento, e apenas então realiza o `Store4` do binding8. Contadores no binding9 indicam operações bem-sucedidas e qualquer operação inválida. O diário tem limite explícito de 32.768 entradas de 32 bytes (1 MiB).
* `scripts/apply_fable_plume53.py` adiciona **buffer Vulkan STORAGE/READBACK** no binding10, com descriptor index70, em overlay separado do 52. O Plume usa o `HOST_COHERENT` do allocator e **só verifica o diário depois do fence de present síncrono**. Valida checksum, formato, alinhamento, endereços, overflow, número de escritas e sobreposição de destinos. Falha fechada se alguma operação não for verificável.
* `port/gpu/fable_memexport_journal53.h` contém verificador C++ e função `Commit` com requisito explícito de exclusão de todos os threads guest; **não chamada pelo Plume neste patch**. Não há suposição artificial de CPU paused.
* O overlay original do Xerenge e a biblioteca `libfable2.so` não são modificados.

## Limitações importantes

**Ainda NÃO é APK jogável nem MemExport de produção:** o registro de operações Vulkan não implica que elas alcancem a RAM convidada; a tradução do shader ainda aceita somente parte dos formatos do Xenos, e não existe exclusão comprovada de todos os threads guest para o commit real. **Os cinco shaders continuam experimentais fora do cache de produção (583/588).** `librexgpu-plume.so` não foi compilada nem testada num celular neste passo. Também existe um limite experimental de 64 MiB para o shadow do binding8; endereços superiores são rejeitados.

O diário registra valores da GPU para viabilizar cópia segura no futuro — mas nenhuma cópia é habilitada até ser comprovado o travamento de guest threads, endianness, máscaras/predicação e o mapeamento de memória física.

## Termux — código público (ZIP sem dados do jogo)

Baixe **Fteste-MemExport-53-Plume-Journal.zip**:

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-53-Plume-Journal.zip -d .
python3 -m unittest discover -s tests -p test_memexport53.py -v
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_memexport53.cpp -o "$HOME/test-fable53"
"$HOME/test-fable53"
python3 scripts/install_fable_plume53.py --root .
python3 scripts/install_fable_plume53.py --root . --check
bash -n scripts/build_fable_gpu.sh
```

```bash
git add scripts/apply_fable_plume53.py scripts/install_fable_plume53.py \
  scripts/upgrade_fable_memexport53_private.py scripts/build_fable_gpu.sh \
  port/gpu/fable_memexport_journal53.h \
  tests/test_memexport53.py tests/test_memexport53.cpp \
  .github/workflows/test-fable-memexport53.yml INSTRUCOES-53.md
git commit -m "Adicionar diario Vulkan MemExport 53 com fence e limites"
git push origin main
```

O workflow público compila testes C++ e executa testes Python SEM jogo.

## ZIP PRIVADO — arquivos derivados do Fable II

Baixe **Fable2-MemExport-53-PRIVADO.zip** e envie APENAS para `NanaveONE/Fable2-Arquivos-Privados`:

```bash
gh release upload guest-input-26 \
  "$HOME/storage/downloads/Fable2-MemExport-53-PRIVADO.zip" \
  --repo NanaveONE/Fable2-Arquivos-Privados --clobber
```

**Jamais** faça `git add` do ZIP privado, SPIR-V/HLSL derivados do jogo, `default.xex` ou arquivos do título no repositório público.

Para habilitar a sonda experimental em uma futura compilação com os shaders 53 integrados, seriam necessários **ambos** `FABLE2_MEMEXPORT52_PROBE=1` e `FABLE2_MEMEXPORT53_JOURNAL=1` no ambiente do processo Android; apenas definir variáveis não integra os shaders privados ao cache nem cria o APK.
