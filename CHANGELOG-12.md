# Fable II Android — Integração 12: 572 shaders reais convertidos com XenosRecomp

## Resultado reproduzido nesta sessão

Os 588 shaders dos dois bancos `Shaders.sbk` / `ShadersRelease.sbk` foram entregues
**diretamente ao XenosRecomp-Linux-x86_64-DXC** compilado pelo GitHub Actions.

- Sem patch: 259 shaders convertidos; 329 pulados pelo DXC (44,05%).
- Com *patch experimental* de textura 1D para uma linha de imagem 2D:
  **572 shaders compilados, 16 pulados (97,28%)**, sendo 450 PS e 122 VS.
- Descompactei o zstd do cache real, conferi todos os offsets e a assinatura
  **SMOL-V** (`LOMS`) dos 572 módulos. Não foi executado `spirv-val` — ele
  precisa dos módulos decodificados de SMOL-V para SPIR-V.
- Por padrão, `validate_xenosrecomp_cache.py` recusa a compilação enquanto a
  cobertura de shaders não for 100%. O cache parcial NÃO deve ser usado como
  se renderizasse o jogo completo.

## Causa raiz predominante, agora isolada

O `shader_common.h` do Xerenge não define `tfetch1D` nem os identificadores
`g_{Recurso}_Texture1DDescriptorIndex` para 7 recursos usados por Fable II.
A correção experimental referencia o mesmo *slot* já associado a Texture2D e
amostra `float2(coord, 0.5)`. **No runtime**, isso só representa textura 1D
corretamente se o Plume construir e vincular essas texturas como imagens 2D
com altura exatamente 1. Nenhum teste de Vulkan/EDRAM foi realizado ainda.

## O que falta no XenosRecomp (16 shaders)

- 10 usam registrador inteiro de laço `i0` não declarado;
- 1 usa registrador inteiro `i16` não declarado;
- 4 exportam interpoladores de vértice maiores que `oTexCoord31`/limite do gerador;
- 1 shader complexo usa temporários `r32`, `r33`, `r34` e múltiplos
  interpoladores adicionais.

Esses casos exigem corrigir a geração de HLSL no código-fonte do XenosRecomp
(e os limites reais do Vulkan). Não resolva trocando variáveis por zero ou
forçando interpoladores para o mesmo índice — isso muda o comportamento do jogo.

## Scripts incluídos

- `scripts/fable_shader_1d_compat.py`: produz um **novo header** compatível
  sem sobrescrever o original.
- `scripts/validate_xenosrecomp_cache.py`: substitui a validação anterior que
  tratava incorretamente os bytes SMOL-V como SPIR-V bruto. Verifica o zstd,
  módulo SMOL-V e cobertura do scanner, podendo recusar caches incompletos.
- `tests/test_fable_shader_compat.py`: testes sintéticos de regressão.

### Exemplo para Linux x86-64

```bash
python scripts/fable_shader_1d_compat.py \
  --header build/host-xenos-artifact/shader_common.h \
  --output build/fable2-shader-common-patched.h

# Com os bancos próprios no PC e o compilador verdadeiro:
python scripts/generate_fable_shaders.py \
  --shader-banks /copia/privada/Shaders.sbk /copia/privada/ShadersRelease.sbk \
  --translator build/host-xenos-artifact/XenosRecomp \
  --header build/fable2-shader-common-patched.h \
  --output build/fable2-shaders

python scripts/validate_xenosrecomp_cache.py \
  --cache build/fable2-shaders/shader_cache.cpp \
  --scan-dir build/fable2-shaders/xenos-scan \
  --min-coverage 1.0
```

Esperado na revisão atual: `INCOMPLETE: 572/588`, exit code 2, corretamente.
O cache derivado é material do jogo: mantenha dentro de `build/`, **não comite
em um repositório GitHub público**. Os dados originais enviados pelo usuário
não estão incluídos neste patch público.

**Situação: shaders em 97,28% traduzidos, não port jogável.**
