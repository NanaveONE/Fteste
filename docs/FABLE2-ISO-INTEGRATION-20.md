# Fable II ISO → Android — integração do MESMO jogo

Fonte de verdade de formato, versão e estrutura: https://github.com/himdo/Fable-2-Recomp (submódulo `external/Fable-2-Recomp` no Fteste).

Este é o **mesmo Fable II GOTY**. Não adaptamos o extrator ou código executável de Burnout Revenge. O fork Xerenge serve somente como referência de execução Android, não como fonte de dados do Fable II.

## Fluxo no celular

1. No app Fable II, selecionar **Selecionar ISO original do Fable II**. O seletor de documentos do Android fornece acesso de leitura à ISO original.
2. O app verifica o cabeçalho GDFX `MICROSOFT*XBOX*MEDIA`, percorre as entradas de diretório (incluindo lotes em vários setores) e localiza `default.xex` e `data/`.
3. Extrai **só** `default.xex` para `Android/data/com.nanaveone.fable2/files/game.pending`, calcula SHA-256 e confere o catálogo de versões que já está implementado em `Fable2GameCompatibility` (GOTY USA/EU e demais edições reconhecidas).
4. Após verificação positiva, extrai `data/` diretamente do FD da ISO para `game.pending/data`, sem copiar a ISO inteira. Não extrai `$SystemUpdate` nem `nxeart`.
5. Confere arquivos obrigatórios e hash do XEX extraído. Somente depois grava `.import-complete` e troca `game.pending` por `game`, preservando a pasta anterior em `game.backup` até a confirmação.
6. Se a biblioteca `libfable2.so` ou o plugin gráfico faltar, o launcher **não tenta fingir que o jogo funciona**: a proteção já existente continua ativa.

**Também continua disponível:** `Importar pasta extraída do Fable II`, para quem já usou `x360extract` fora do Android.

### Limitações explícitas

- O `ContentResolver` precisa fornecer um FD com acesso aleatório. Alguns provedores de nuvem entregam streams sem seek: nesse caso, copie a ISO para um armazenamento local e selecione-a novamente.
- A instalação precisa de espaço suficiente para os arquivos extraídos do Fable II (vários GB), ainda que a ISO não seja duplicada.
- Leitura e instalação transacional do layout GDFX foram validadas com imagens e interfaces SAF sintéticas, **não com ISO comercial real dentro deste ambiente**. O comportamento em diferentes provedores SAF e a velocidade em telefone precisam ser testados.
- GDFX não é ISO9660 puro. ISOs compactadas, fragmentadas ou não-ripadas integralmente podem não funcionar.
- Integração de dados não soluciona C++ ARM64, shader translation, Vulkan, EDRAM, áudio, saves ou gameplay.

## Referência exata ao upstream

- `tools/x360extract/lib/Gdfx.cs`: cabeçalho 36 bytes, setor 2048 bytes, base `header - 0x10000`, entradas variáveis e preenchimento 0xFF entre setores.
- `tools/x360extract/lib/X360Disc.cs`: seleção de arquivos e cópia em chunks.
- `launcher/Fable2.Launcher/DiscExtraction.cs`: fluxo original: verificar XEX antes da extração de data.
- `constants/game_versions.json`: identificadores SHA-256 reconhecidos do Fable II.

No Linux/Windows, `scripts/extract_fable_iso_upstream.py` executa o **código original .NET 8** sem modificar o extrator. No Android, a implementação Java usa a mesma estrutura GDFX (não exige instalar .NET no aparelho).
