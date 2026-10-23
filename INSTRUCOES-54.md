# Fable II MemExport — CI54: verificação de 52 com 53 instalado

**Causa observada:** a execução Actions 40031520327 falhou no `install_fable_plume52.py --check` porque o patch 53 substituiu corretamente o bloco final `plume_overlay` 52. Os testes unitários 52 e 53 passaram.

O verificador agora reconhece a extensão **exata** da versão 53, reconstrói a versão 52 somente em memória e valida a antiga âncora. Não toca no `scripts/build_fable_gpu.sh`, não modifica o upstream Xerenge, não lê dados do jogo e rejeita quaisquer mudanças não esperadas em 52 ou 53.

## No Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-Plume-CI-54.zip -d .
python3 -m unittest discover -s tests -p test_memexport52.py -v
python3 scripts/install_fable_plume52.py --root . --check
python3 scripts/install_fable_plume53.py --root . --check
git add scripts/install_fable_plume52.py tests/test_memexport52.py INSTRUCOES-54.md
git commit -m 'Corrigir verificacao Plume52 sobre Plume53 (54)'
git push origin main
```

O workflow original da correção 52 deverá rodar novamente com esse commit. Verifique com:

```bash
gh run list --repo NanaveONE/Fteste --workflow test-fable-memexport52.yml --limit 3
```

**Limitação:** isto resolve exclusivamente a regressão de CI. A sincronização real das escritas MemExport com a RAM convidada e a validação `librexgpu-plume.so` no Android ainda estão pendentes. Cache de produção permanece em 583/588.
