# Correção 43: relatório privado dos cinco shaders memexport

Esta correção **não faz os cinco shaders passarem** e **não libera um APK**. Ela corrige a ausência de um relatório privado reproduzível no workflow 40, para desenvolver a implementação correta de exportação de memória da GPU Xenos no Plume. O limite de 100% dos 588 shaders permanece obrigatório no workflow.

Confirmado no log fornecido: 583/588 (99,15%). Cinco shaders falharam por `FABLE2_MEMEXPORT_REQUIRES_PLUME_VULKAN_STORAGE_BUFFER_SUPPORT`: `17A0FEDEF93DAE25`, `1CEC1A730807EC21`, `5243696187782727`, `AC0C424248A6B1AD`, `DB2ACD9856EB8E28`.

## Instalar no Termux

Depois de baixar `Fteste-Fable2-Memexport-43.zip` em Downloads:

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-Fable2-Memexport-43.zip -d .
python3 -m unittest discover -s tests -p 'test_report_fable_memexport_43.py' -v
python3 scripts/enable_shader_diagnostics_43.py
python3 scripts/enable_shader_diagnostics_43.py --check
git add .github/workflows/build-fable2-shaders-40.yml scripts/enable_shader_diagnostics_43.py scripts/report_fable_memexport_43.py tests/test_report_fable_memexport_43.py INSTRUCOES-43.md
git commit -m 'Salvar diagnostico privado dos shaders memexport 43'
git push origin main
```

## Gerar o diagnóstico no Actions

```bash
gh workflow run build-fable2-shaders-40.yml --repo NanaveONE/Fteste --ref main -f release_tag=guest-input-26 -f xenos_run_id=39986495904
```

O workflow deverá **continuar FAILED**, porque memexport ainda não foi implementado. Depois da falha, a release privada deve conter o asset `Fable2-MemExport-DIAGNOSTICO-43.zip` (gerado apenas se o cache parcial existir e o token privado conseguir publicar).

```bash
gh release download guest-input-26 --repo NanaveONE/Fable2-Arquivos-Privados --pattern 'Fable2-MemExport-DIAGNOSTICO-43.zip' --dir ~/storage/downloads/Fable2
```

O diagnóstico contém HLSL derivado do jogo e cache parcial. **Nunca** faça commit ou Actions artifact público desse diagnóstico. Envie somente de forma privada quando for necessário investigar os cinco shaders.

## Pendências técnicas reais

- Tradutor XenosRecomp: traduzir `ExportAddress` (32) e `ExportData0..4` (33..37) em instruções que preservem semântica de escrita de memória do Xenos.
- Plume/Vulkan: alocar, vincular e sincronizar storage buffers com memória convidada, observando endereços, formatos, ordenação e barreiras de memória.
- Plume: fornecer o banco de constantes inteiras do patch 42 no descriptor set 0 / binding 7; atualmente o shader espera esse binding, mas o Plume ainda não o fornece.
- Plume: implementar a compatibilidade de texturas 1D do patch 41, que atualmente assume views 2D com altura 1.

Este pacote não mexe em `libfable2.so` nem exige enviar novamente `Shaders.sbk` ou `ShadersRelease.sbk` à release privada.
