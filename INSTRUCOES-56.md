# Fable II — correção 56: compilação ARM64 privada de diagnóstico

## Objetivo

Tentar construir o **verdadeiro** `librexgpu-plume.so` para Android ARM64 com
as camadas Plume 46 → 52 → 53 → 55, usando o cache de **583/588** módulos
originalmente gerado dos dois bancos de shaders privados. Cinco vertex shaders
MemExport continuam **ausentes** do cache de produção; não inventamos stubs.
O objetivo é descobrir erros de compilação/linkedição/ABI do plugin antes de
terminar a semântica MemExport. Isso NÃO é um APK jogável.

## Instalacao Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-GPU-ARM64-Probe-56.zip -d .
python3 -m unittest discover -s tests -p test_gpu_probe56.py -v
python3 scripts/enable_fable_gpu_probe56.py --root .
python3 scripts/enable_fable_gpu_probe56.py --root . --check
bash -n scripts/build_fable_gpu.sh

git add scripts/enable_fable_gpu_probe56.py scripts/validate_gpu_probe56.py \
  scripts/build_fable_gpu.sh tests/test_gpu_probe56.py \
  .github/workflows/test-fable-gpu-probe56.yml \
  .github/workflows/build-fable-gpu-probe56-private.yml INSTRUCOES-56.md
git commit -m 'Adicionar compilacao diagnostica GPU ARM64 56'
git push origin main
```

## Iniciar o workflow de compilacao (somente apos enviar o commit)

```bash
gh workflow run build-fable-gpu-probe56-private.yml \
  --repo NanaveONE/Fteste --ref main \
  -f release_tag=guest-input-26 -f xenos_run_id=39971826822
```

O workflow exige o secret `FABLE2_PRIVATE_TOKEN` com acesso à release privada
`NanaveONE/Fable2-Arquivos-Privados/guest-input-26`, que deve conter
`Shaders.sbk`, `ShadersRelease.sbk` e `Fable2-MemExport-DIAGNOSTICO-43.zip`.
Sem eles, falha de forma segura. NUNCA envie tais arquivos ao GitHub público.

Se a compilação ARM64 terminar com sucesso, somente a release **privada** recebe
`Fable2-Plume-ARM64-Probe56-PRIVADO.zip` (librexgpu-plume.so + relatório + aviso).
Não há upload público de artefatos, e logs potencialmente proprietários são
redirecionados para arquivos locais e eventualmente enviados à release privada
sob `Fable2-GPU-Probe56-LOGS-PRIVADO.zip`, apenas se houver falha.

## Protecoes

- O modo padrão `bash scripts/build_fable_gpu.sh` continua exigindo 588/588.
- Somente `FABLE2_GPU_PROBE56=1` **com** o diagnóstico privado exato habilita
  a tentativa 583/588.
- O cache precisa corresponder byte a byte à cópia do diagnóstico 43; os cinco
  hashes conhecidos, 132 VS + 451 PS e a origem SBK são validados.
- O linker do plugin Android passa a exigir alinhamento ELF de **16 KiB**.
- O `libfable2.so` compilado anteriormente **não é recompilado nem modificado**.
- A execução gráfica, a exclusão global das threads do jogo e a tradução
  correta dos cinco MemExport ainda precisam de desenvolvimento e testes.
