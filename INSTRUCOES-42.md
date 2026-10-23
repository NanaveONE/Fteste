# XenosRecomp 42: correção dos 16 shaders pendentes (etapa parcial)

Esta correção **NÃO afirma que os 588 shaders foram traduzidos**. A correção
41 atingiu 572/588. No log, os erros remanescentes são temporários r32..r34,
constantes de loop i0/i16 e exportações GPU 32..36.

Implementado:

1. Amplia o banco de temporários C++ para 64 registradores (`r0..r63`).
2. Cria um bloco explícito Vulkan em `set=0, binding=7` para os `i0..i31`
   não definidos estaticamente pelo shader; as definições presentes no próprio
   shader têm precedência. **Para rodar, o Plume ainda deve preencher essa UBO
   com os valores corretos do jogo.** Sem integração, isso não é jogável.
3. Detecta memexport (`ExportAddress`, `ExportData0..4`) e marca a shader com
   `#error FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT`.
   Isso evita o erro anterior `oTexCoord32..36` e, principalmente, evita
   descartar efeitos GPU em silêncio. O backend de memexport ainda está pendente.
4. Fixa a revisão do XenosRecomp, valida âncoras exatas e publica somente
   o compilador público. O workflow de shaders privados mantém o critério 100%.

## Aplicar no Android/Termux

Depois de salvar `Fteste-XenosRecomp-42.zip` em Downloads:

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-XenosRecomp-42.zip -d .
python3 -m unittest discover -s tests -p 'test_fix_xenos_fable42.py' -v

git add .github/workflows/build-xenos-host.yml \
  scripts/fix_xenos_fable42.py tests/test_fix_xenos_fable42.py \
  INSTRUCOES-42.md
git commit -m 'XenosRecomp 42: reg64 e constantes de loop explicitas'
git push origin main
```

Inicie o tradutor recompilado:

```bash
gh workflow run build-xenos-host.yml --repo NanaveONE/Fteste --ref main
```

Para acompanhar e obter o ID da execução **nova**:

```bash
gh run list --repo NanaveONE/Fteste --workflow build-xenos-host.yml --limit 3
```

Assim que o novo XenosRecomp terminar com sucesso, teste a tradução privada:

```bash
RUN_ID=$(gh run list --repo NanaveONE/Fteste \
  --workflow build-xenos-host.yml \
  --json databaseId,conclusion --limit 10 \
  --jq '[.[] | select(.conclusion=="success")][0].databaseId')
test -n "$RUN_ID" && test "$RUN_ID" != null || exit 2

gh workflow run build-fable2-shaders-40.yml \
  --repo NanaveONE/Fteste --ref main \
  -f release_tag=guest-input-26 -f xenos_run_id="$RUN_ID"
```

O teste de shaders pode continuar falhando **por memexport ainda não
implementado no backend Vulkan**. Este é um bloqueio real do renderizador,
não um motivo para mascarar o erro ou declarar 100% sem suporte. Não envie
arquivos derivados do jogo ao repositório público; o workflow existente
continua acessando os SBK somente da release privada.
