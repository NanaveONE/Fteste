# Fable II Android — Integração 10: shaders reais dos bancos SBK

## Evidência real, a partir de cópias privadas enviadas pelo usuário

A análise de `Shaders.sbk` e `ShadersRelease.sbk` GOTY US/EU identificou:

| Arquivo | Versão SBK | Blocos zlib Z_SYNC_FLUSH | Bytes descompactados | VS | PS |
|---|---|---:|---:|---:|---:|
| Shaders.sbk | 0x0301 | 147 | 1.942.172 | 137 | 451 |
| ShadersRelease.sbk | 0x0300 | 147 | 1.802.572 | 137 | 451 |

Os 588 contêineres Xenos do tipo `0x102A11` em cada arquivo são idênticos por SHA-256.
Os bancos apresentam metadados e comprimentos diferentes, mas contêm as mesmas
137 definições de vertex shader e 451 de pixel shader. O formato foi analisado
localmente sem publicar bytecode ou conteúdo do jogo.

## Implementação

- `scripts/extract_fable_sbk.py`: identifica o cabeçalho `ShaderBankFile`,
  valida versões 0x0300/0x0301, recupera blocos zlib de tamanho prefixado com
  `Z_SYNC_FLUSH`, verifica limites/tabelas de cada bloco, extrai contêineres
  Xenos `0x102A11` e remove duplicatas por SHA-256.
- `scripts/find_fable_shader_banks.py`: localiza `data/Shaders` ou `data/shaders`
  no Linux sem assumir a mesma capitalização do manifesto Xbox 360.
- `scripts/generate_fable_shaders.py`: nova opção `--shader-banks` para gerar o
  cache SPIR-V pelo XenosRecomp, em vez de tentar encontrar os shaders no XEX.
  Mantém as opções anteriores de decodificar imagens XEX para casos adicionais.
- `scripts/attempt_playable_build.sh`: opta pelos SBKs reais, valida a proveniência
  do cache entre compilações e não exige mais extrator XEX para obter os shaders
  estáticos. A compilação de shaders capturados em tempo de execução exige
  `FABLE2_DECODED_GUEST_IMAGE` para verificar origem.
- `scripts/playable_preflight.py`: verifica presença de ao menos um banco SBK.
- Testes com arquivos **sintéticos** reproduzem a extração sem distribuir dados
  do Fable II; o GitHub Actions testa somente o código-fonte.

## Uso local

```bash
python3 scripts/extract_fable_sbk.py \
  --banks /copia/privada/Fable2/data/Shaders/Shaders.sbk \
          /copia/privada/Fable2/data/Shaders/ShadersRelease.sbk \
  --output build/sbk-extraido

# Se o XenosRecomp host já estiver compilado:
python3 scripts/generate_fable_shaders.py \
  --shader-banks /copia/privada/Fable2/data/Shaders/Shaders.sbk \
                 /copia/privada/Fable2/data/Shaders/ShadersRelease.sbk \
  --translator "$FABLE2_SHADER_TRANSLATOR" \
  --header "$XENOS_RECOMP_ROOT/XenosRecomp/shader_common.h" \
  --output build/fable2-shaders
```

**Limites:** extração de bytecode NÃO é compilação para SPIR-V. A execução real
com XenosRecomp e a compilação do plugin Vulkan não puderam ser testadas neste
ambiente sem suas dependências nativas. Shaders gerados dinamicamente durante o
jogo podem não estar nesses bancos. O suporte às rotinas de GPU/EDRAM e o port
ARM64 completo também continuam pendentes. Não há APK jogável validado.
