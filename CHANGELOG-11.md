# Fable II Android — Integração 11: validação da tradução SPIR-V (sem APK falso)

## Evidências coletadas com os arquivos reais do usuário (não incluídos neste pacote)

- `Shaders.sbk` / `ShadersRelease.sbk`, edição GOTY US/EU;
- 588 contêineres únicos: 137 VS e 451 PS;
- 576 sequências únicas de microcódigo (12 contêineres compartilham microcódigo);
- **zero** problemas de alinhamento/tamanho nos cabeçalhos `Shader`/`ShaderContainer` que o XenosRecomp utiliza.

Esses resultados vêm da análise do conteúdo real fornecido, não de um tradutor simulado.

## Problema identificado na etapa anterior

O comando XenosRecomp pode **ignorar shaders quando o DXC falha e ainda assim
escrever um `shader_cache.cpp`**. Os testes anteriores só conferiam presença de
símbolos C++ e não descompactavam/inspecionavam os módulos SPIR-V. Um arquivo
com contagem zero/incompleta podia seguir para o Vulkan.

## Implementações

- `scripts/audit_xenosrecomp_inputs.py`: confirma limites, campo `physicalOffset`,
  tamanho e alinhamento de instrução Xenos de cada contêiner SBK.
- `scripts/validate_xenosrecomp_cache.py`: lê o C++ emitido pelo XenosRecomp,
  extrai e descompacta o zstd, confere limites de cada módulo SPIR-V,
  verifica o cabeçalho e a estrutura de instruções, e reconcilia os arquivos
  `PS_*/VS_*` de entrada com as entradas realmente compiladas. Opcional:
  `--spirv-val` para validação externa completa. Relatório apenas estatístico.
- `scripts/attempt_playable_build.sh` e `scripts/build_fable_gpu.sh` agora
  **exigem 100% de cobertura estática** antes da compilação ARM64 de GPU.
- `scripts/translate_fable_sbk_real.sh`: compila **o XenosRecomp real** com seu
  DXC e traduz os bancos privados; ou aceita o compilador pronto da CI
  (`XENOSRECOMP_HOST_DIR`). Não usa bytecode falso, não baixa jogo.
- `.github/workflows/build-xenos-host.yml`: build público do XenosRecomp/DXC
  Linux x86_64, com upload-artifact de binário, cabeçalho e biblioteca DXC,
  **sem nenhum arquivo de Fable II**.
- Testes unitários com SPIR-V sintético positivo/negativo. Não se confunde
  teste sintético com tradução dos shaders reais.

## Como concluir a tradução real usando os dois SBKs privados

### Opção A — computador Linux x86_64 com Git e dependências

```bash
bash scripts/setup_gpu_dependencies.sh
bash scripts/translate_fable_sbk_real.sh \
  /pasta/privada/Shaders.sbk /pasta/privada/ShadersRelease.sbk
```

O script exige uma build DXC/XenosRecomp genuína, produz cache em
`build/fable2-shaders/` e recusa cobertura inferior a 100%.

### Opção B — compilador pronto via GitHub Actions

1. Publique o código-fonte deste ZIP no Fteste.
2. Execute o workflow **Compilar XenosRecomp Linux DXC (sem arquivos de jogo)**.
3. Baixe o artefato **XenosRecomp-Linux-x86_64-DXC** e extraia em
   `build/host-xenos-artifact/` num Linux x86_64.
4. Rode:

```bash
XENOSRECOMP_HOST_DIR="$PWD/build/host-xenos-artifact" \
  bash scripts/translate_fable_sbk_real.sh \
  /pasta/privada/Shaders.sbk /pasta/privada/ShadersRelease.sbk
```

Opcional para validar SPIR-V via SPIRV-Tools:

```bash
python3 scripts/validate_xenosrecomp_cache.py \
  --cache build/fable2-shaders/shader_cache.cpp \
  --scan-dir build/fable2-shaders/xenos-scan \
  --report build/fable2-shaders/spirv-coverage-report.json \
  --spirv-val
```

**Nenhuma cópia de SBK, microcódigo, HLSL ou SPIR-V proprietário deve entrar
no GitHub público.** Os caches e logs de compilação permanecem no diretório
`build/` ignorado pelo `.gitignore`.

## Estado verificado

Este ambiente tem `clang++` mas **não tem XenosRecomp, DXC nem conexão para
baixar os repositórios**, de modo que **não foi possível executar aqui a
compilação real dos 588 shaders**. Foram verificados os contêineres reais e
executados os testes do verificador de saída com SPIR-V sintético.

O primeiro arquivo necessário para executar a tradução aqui é o artefato
open-source `XenosRecomp-Linux-x86_64-DXC` do workflow (não o jogo).
A tradução SPIR-V não resolve por si só EDRAM, render targets e gameplay.
